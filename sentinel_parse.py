"""
Sentinel-V — parser + safety checks (the "runway brain" input layer)

Turns a Prisma transcript into facts, and refuses to guess:
  CONFIRMED : runway + callsign extracted and both make sense at this airport
  FLAGGED   : something is impossible or missing -> ask a human ("say again")
Only a CONFIRMED-but-wrong result is dangerous. We measure that separately.
"""

import re

# ---------------------------------------------------------------------------
# Airports: real runway designators
# ---------------------------------------------------------------------------
AIRPORTS = {
    "VABB": {"name": "Mumbai", "runways": {"09", "27", "14", "32"}},
    "VIDP": {"name": "Delhi", "runways": {"09", "27", "10", "28", "11L", "29R", "11R", "29L"}},
    "VAPO": {"name": "Pune", "runways": {"10", "28"}},
}

# Radio callsign word -> airline code
# NOTE: Vistara merged into Air India (Nov 2024). "VISTARA" is kept ONLY to replay the
# Delhi Aug-2023 incident; live traffic today would be Air India.
AIRLINES = {"IFLY": "IGO", "AIR INDIA": "AIC", "VISTARA": "VTI", "AKASA AIR": "AKJ"}
VEHICLES = {"FOLLOW ME": "FOLLOWME", "BIRD CHASER": "BIRDCHASER"}

DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "tree": "3", "four": "4",
    "fower": "4", "five": "5", "fife": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "niner": "9", "ight": "8",   # "ight": eight with the e lost (A3 + dev2: 5 times, 2 voices)
    "nayana": "9", "liner": "9", "minor": "9",
    "ज़ीरो": "0", "झिरो": "0", "जीरो": "0", "वन": "1", "टू": "2", "थ्री": "3", "फोर": "4",
    "फाइव": "5", "फाईव्ह": "5", "फाइव्ह": "5", "सिक्स": "6", "सेवन": "7", "सेव्हन": "7", "एट": "8",
    "नाइन": "9", "नाईन": "9",
}
SIDE = {"right": "R", "left": "L", "centre": "C", "center": "C",
        "r": "R", "l": "L", "c": "C", "राइट": "R", "लेफ्ट": "L"}
FIXES = [
    (r"\bi\s*f\s*l\s*y\b|\bi\s*(flee|please)\b", "IFLY"),   # "I fly", "IFL Y", "IFLY"
    (r"(\d)\s*er\b", r"\1"),                                  # "29er" = "two niner" with the "nin" eaten
    (r"\bair\s*india\b", "Air India"),
    (r"\bfollow\s*me\b|फॉलो\s*मी", "Follow Me"),
    (r"\bbird\s*(chaser|chester)\b|बर्ड\s*चेसर", "Bird Chaser"),
    (r"रनवे", "runway"),
    (r"टॅक्सीवे|टैक्सीवे", "taxiway"),
    (r"टॉवर|टावर", "tower"),
]
PUNCT = set(",.।!?:;")

# Experiment A14 (7 Nov), Fix T: "Vistara" heard as "Tara" - 24 times in the saved DEL_2023 runs, from 2 voices
# (tower Avinash 20, pilot Harshad 4), and never anything else. Only when a number follows ("Tara, 926").
# Off until exp_a14.py passes its rules (written in that file before the result).
TARA_ALIAS = False

# Experiment A16 (7 Nov), Fix R: runway side "right" heard as "arrive(d)" right after a runway number ("runway 29, arrived").
# Practice data before the exam: 5 times, ONE voice only - not enough. The rule in exp_a16.py was written BEFORE the new
# practice run with the exam's v2.5 voices (noise recordings 200-209).
# RESULT: FAIL (only 3 calls lost a flag, one voice; needs 8 from 2+). The new voices rarely said "arrived". Kept off.
ARRIVE_AS_RIGHT = False

# Decision switch (your call): True = a callsign with a look-alike from the same airline on
# frequency (5134/5124, 2817/2871) is shown AMBER, never green. False = old behaviour.
SIMILAR_CALLSIGN_CAUTION = True


# "eight" written as the letter A glued to a number: 915A (9158), 746A (7468), 273A (2738),
# runway 2A (28) - 4 of 4 right, 3 voices, dev + dev2 + step1. Other glued letters are NOT mapped:
# C was 3 twice but 2 once ("3C" for 32); B/P after a runway is Hindi "pe" ("28B" = "28 pe").
EIGHT_AS_A = re.compile(r"\b(\d+)A\b")


def normalize(text):
    t = EIGHT_AS_A.sub(lambda m: m.group(1) + "8", text)
    if ARRIVE_AS_RIGHT:
        t = re.sub(r"\b(\d{1,2})\s*[,.]?\s*arriv(?:e|ed|es)\b", r"\1 right", t, flags=re.IGNORECASE)
    if TARA_ALIAS:
        t = re.sub(r"\btara\b(?=[\s,.]*\d)", "Vistara", t, flags=re.IGNORECASE)
    for pat, rep in FIXES:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = re.sub(r"(\d)([A-Za-zऀ-ॿ])", r"\1 \2", t)
    t = re.sub(r"([A-Za-zऀ-ॿ])(\d)", r"\1 \2", t)
    t = re.sub(r"([,.।!?:;])", r" \1 ", t)
    tokens = t.split()

    def is_digit_tok(x):
        return x.lower() in DIGIT_WORDS or x.isdigit()

    out, i = [], 0
    while i < len(tokens):
        if is_digit_tok(tokens[i]):
            after_runway = bool(out) and out[-1].lower() == "runway"
            num = ""
            while i < len(tokens):
                if is_digit_tok(tokens[i]):
                    num += DIGIT_WORDS.get(tokens[i].lower(), tokens[i]); i += 1
                # "runway 2, 9R": a comma inside a runway number is Prisma punctuation, not speech
                elif after_runway and tokens[i] in PUNCT and i + 1 < len(tokens) \
                        and is_digit_tok(tokens[i + 1]) and len(num) < 2:
                    i += 1
                else:
                    break
            # side letter, skipping commas: "29, right" -> 29R ; "29R right" -> 29R
            j = i
            while after_runway and j < len(tokens) and (tokens[j] in PUNCT or tokens[j].lower() in SIDE):
                if tokens[j].lower() in SIDE and not num[-1].isalpha():
                    num += SIDE[tokens[j].lower()]
                    i = j + 1
                elif tokens[j].lower() in SIDE:
                    i = j + 1
                j += 1
            out.append(num)
            continue
        out.append(tokens[i]); i += 1
    s = " ".join(out)
    return re.sub(r"\s+([,.।!?:;])", r"\1", s).strip()


# Words after which a number is NEVER a flight number.
NOT_CALLSIGN_BEFORE = {"RUNWAY", "WIND", "DEGREES", "HEADING", "SQUAWK", "LEVEL", "QNH",
                       "KNOTS", "FEET", "ALTITUDE", "FREQUENCY", "CONTACT", "GATE", "STAND", "BAY"}


# Experiment A15 (7 Nov), Fix S: the airline word glued onto the flight number as digits ("15725" for "Vistara 725",
# "36053" for "IFLY 6053", "37982" for "IFLY 3798"): a 5-6 digit number cannot be a flight number. If its LAST digits are
# exactly ONE flight on frequency, take that flight - always AMBER ("confirm callsign"), never green, never a changed digit.
# Seen 76 times in the practice runs, many voices. Off until exp_a15.py passes its rules (written there first).
SUFFIX_CALLSIGN = True


# Experiment A17 (7 Nov), Fix G: a runway number glued after "niner" with the SIDE heard ("runway 290, right",
# "298R", "2900R"): in all saved practice transcripts the first two digits were right 61 of 61 and the side 48 of 48.
# Only "X9 + 1-2 extra digits + side", only if X9+side exists here. Always AMBER, the heard form is shown.
GLUE_RUNWAY_SIDE = True
GLUE_RE = re.compile(r"\b(runway\s+)(\d9)(\d{1,2})([LRC])\b", re.IGNORECASE)

# Experiment A17, Fix N: "niner" written 90 INSIDE a 4-5 digit flight number ("Tara 9026" for "Vistara niner two six",
# 10 of 10 in the saved transcripts). Only that form: 4 digits, ONE "0" dropped right after a "9" (5-digit glue and
# 98/99 stay with A3's second listen: "98714" can really be "nine eight seven one four"). It must give exactly ONE
# flight on frequency, the raw number none - always AMBER ("confirm callsign"), never green.
NINER0_CALLSIGN = True


def niner0_callsign(up, expected_traffic):
    toks = re.findall(r"[A-Z]+|\d+", up)
    edge = set(range(min(3, len(toks)))) | set(range(max(0, len(toks) - 3), len(toks)))
    flights = [f for f in expected_traffic if f[:3] in AIRLINES.values()]
    nums = {f[3:] for f in flights}
    hits = set()
    for i in sorted(edge):
        t = toks[i]
        if t.isdigit() and len(t) == 4 and t not in nums and not (i > 0 and toks[i - 1] in NOT_CALLSIGN_BEFORE):
            ok = {t[:j + 1] + t[j + 2:] for j in range(len(t) - 1) if t[j] == "9" and t[j + 1] == "0"}
            hits |= {(f, t) for f in flights if f[3:] in ok}
    if len({f for f, _ in hits}) == 1:
        return next(iter(hits))
    return None


def suffix_callsign(up, expected_traffic):
    toks = re.findall(r"[A-Z]+|\d+", up)
    edge = set(range(min(3, len(toks)))) | set(range(max(0, len(toks) - 3), len(toks)))
    flights = [f for f in expected_traffic if f[:3] in AIRLINES.values()]
    hits = set()
    for i in sorted(edge):
        t = toks[i]
        if t.isdigit() and 5 <= len(t) <= 6:
            hits |= {(f, t) for f in flights if t.endswith(f[3:]) and 1 <= len(t) - len(f[3:]) <= 2}
    if len({f for f, _ in hits}) == 1:
        return next(iter(hits))
    return None


def anchor_callsign(up, expected_traffic):
    """
    Used ONLY when no airline word was recognised (e.g. Prisma wrote "Air France 5134" or "Reply 2241"
    for IFLY). ICAO phraseology puts the callsign FIRST in a controller call and LAST in a readback,
    so we look only at the first 3 and last 3 words.
    A number there must EXACTLY equal the flight number of ONE aircraft on frequency.
    We never change a digit. Two matches, or no exact match -> nothing (stays FLAG).
    """
    toks = re.findall(r"[A-Z]+|\d+", up)
    words = [t for t in toks]
    edge = set(range(min(3, len(words)))) | set(range(max(0, len(words) - 3), len(words)))
    nums = []
    for i in sorted(edge):
        t = words[i]
        if t.isdigit() and 2 <= len(t) <= 4 and not (i > 0 and words[i - 1] in NOT_CALLSIGN_BEFORE):
            nums.append(t)
    flights = [f for f in expected_traffic if f[:3] in AIRLINES.values()]
    hits = {f for n in nums for f in flights if f[3:] == n}
    if len(hits) > 1:
        # two airlines share the number (AIC4822 + IGO4822). A garbled airline word right before
        # the number may still be ONE edit from exactly one airline word: "IFL"/"FLY" -> IFLY.
        word_of = {code: w.split()[0] for w, code in AIRLINES.items()}
        near = set()
        for i, t in enumerate(words):
            if t.isdigit() and i > 0 and len(words[i - 1]) >= 3 and not words[i - 1].isdigit():
                near |= {f for f in hits if f[3:] == t and edit_distance(words[i - 1], word_of[f[:3]]) <= 1
                         and words[i - 1] != word_of[f[:3]]}
        hits = near
    if len(hits) == 1:
        return hits.pop()
    return None


def edit_distance(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[-1]


def edit1(a, b):
    """True if a and b differ by at most one insert/delete/substitute."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = sorted((a, b), key=len)
    return any(l[:k] + l[k + 1:] == s for k in range(len(l)))


def confusable(a, b):
    """Two flight numbers a listener can mix up: one digit different (5134/5124)
    or two neighbouring digits swapped (2817/2871). Eurocontrol's call-sign-similarity
    work treats exactly these as the risky pairs."""
    if a == b or len(a) != len(b):
        return edit1(a, b) and a != b
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) == 1:
        return True
    return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]


def similar_on_frequency(cs, expected_traffic):
    code, num = cs[:3], cs[3:]
    return sorted(t for t in expected_traffic if t != cs and t[:3] == code and confusable(num, t[3:]))


def extract(text, airport, expected_traffic, glue=True):
    """
    expected_traffic: callsigns known to be on frequency (from schedule/ADS-B), e.g. {"IGO6053"}
    Returns dict with runway, callsign and a list of problems.
    """
    norm = normalize(text)
    glue_note = None
    if GLUE_RUNWAY_SIDE and glue:
        g = GLUE_RE.search(norm)
        if g and f"{g.group(2)}{g.group(4).upper()}" in AIRPORTS[airport]["runways"]:
            glue_note = (f"runway heard as {g.group(2)}{g.group(3)}{g.group(4).upper()} ('niner' glued); "
                         f"read as {g.group(2)}{g.group(4).upper()} - confirm")
            norm = norm[:g.start()] + g.group(1) + g.group(2) + g.group(4).upper() + norm[g.end():]
    up = norm.upper()
    problems, out = [], {"normalized": norm, "runway": None, "callsign": None, "raw": text,
                         "corrected": False, "suggestion": None, "amber": [glue_note] if glue_note else []}

    m = re.search(r"RUNWAY\s+(\d{1,2}[LRC]?)\b", up)
    if not m:
        problems.append("no runway heard")
    else:
        digits, side = re.match(r"(\d+)([LRC]?)", m.group(1)).groups()
        rwy = digits + side
        if len(digits) == 1:
            # ICAO runways are always spoken as two digits ("zero niner"). One digit means a
            # digit was lost ("two niner" -> "9"), and padding it to 09 could create a REAL runway.
            problems.append(f"only one runway digit heard ({digits}) - say again")
        elif rwy in AIRPORTS[airport]["runways"]:
            out["runway"] = rwy
        else:
            problems.append(f"runway {rwy} does not exist at {AIRPORTS[airport]['name']}")

    for word, code in VEHICLES.items():
        if word in up:
            vm = re.search(word + r"\W*(\d+)", up)
            # "Follow Me two" heard as "Follow Me to" / "Bird Chaser, तू" (dev run: 5 times, always "two").
            # Only directly after the vehicle name, never anywhere else, and shown AMBER.
            vm_to = None if vm else re.search(word + r"[\s,]*(?:TO|तू)(?=[\s,।.]|$)", up)
            if vm_to:
                cs = code + "2"
                vehicles_known = {t for t in expected_traffic if t.startswith(code)}
                if vehicles_known and cs not in vehicles_known:
                    problems.append(f"{cs} is not an active vehicle")
                else:
                    out["callsign"] = cs
                    out["amber"].append(f"vehicle number heard as 'to' - probably {word.title()} 2, confirm")
            elif not vm:
                # "Follow Me" with no number: we don't know WHICH vehicle -> never confirm
                problems.append(f"{word.title()} number not heard")
            else:
                cs = code + vm.group(1)
                vehicles_known = {t for t in expected_traffic if t.startswith(code)}
                if vehicles_known and cs not in vehicles_known:
                    problems.append(f"{cs} is not an active vehicle")
                else:
                    out["callsign"] = cs
            break
    else:
        for word, code in AIRLINES.items():
            cm = re.search(re.escape(word) + r"\W*(\d{2,4}[A-Z]?)\b", up)
            if cm:
                cs = code + cm.group(1)
                if cs in expected_traffic:
                    out["callsign"] = cs
                else:
                    heard = cm.group(1)
                    near = [t for t in expected_traffic if t.startswith(code) and edit1(t[3:], heard)]
                    # only auto-correct if NO other flight is even 2 edits away (else it's a coin toss)
                    rivals = [t for t in expected_traffic if t not in near and t.startswith(code)
                              and edit_distance(t[3:], heard) <= 2]
                    # NO auto-correct. "5124" could be Prisma mishearing 5134, OR a pilot really
                    # saying the wrong callsign (the #1 real-world radio mix-up). The text is identical
                    # in both cases, so a human must decide. We only SUGGEST the closest flight.
                    if len(near) == 1 and not rivals:
                        out["suggestion"] = near[0]
                        problems.append(f"callsign {cs} not on frequency - did they mean {near[0]}?")
                    else:
                        problems.append(f"callsign {cs} not expected on frequency")
                break
        else:
            hit = anchor_callsign(up, expected_traffic)
            hit2 = None if hit or not SUFFIX_CALLSIGN else suffix_callsign(up, expected_traffic)
            hit3 = None if hit or hit2 or not NINER0_CALLSIGN else niner0_callsign(up, expected_traffic)
            if hit3:
                out["callsign"] = hit3[0]
                out["amber"].append(f"flight number heard as {hit3[1]} ('niner' glued); undone it matches "
                                    f"{hit3[0]} exactly - confirm callsign")
            elif hit:
                out["callsign"] = hit
                out["amber"].append(f"callsign not in the usual airline+number form; number matches {hit} exactly")
            elif hit2:
                cs2, heard_num = hit2
                out["callsign"] = cs2
                out["amber"].append(f"flight number heard with extra digits in front ({heard_num}); "
                                    f"its last digits match {cs2} exactly - confirm callsign")
            else:
                problems.append("no callsign heard")

    # A heard callsign that has a look-alike twin on frequency is never shown green:
    # a "three"/"two" slip would land on the OTHER real flight and pass every other check.
    cs = out["callsign"]
    if SIMILAR_CALLSIGN_CAUTION and cs and cs[:3] in AIRLINES.values():
        twins = similar_on_frequency(cs, expected_traffic)
        if twins:
            out["amber"].append(f"similar callsign on frequency: {', '.join(twins)}")

    if EIGHT_AS_A.search(text):
        out["amber"].append("a digit was heard as the letter A and read as 8 - confirm")
    out["problems"] = problems
    # CONFIRMED = everything heard cleanly.  PROBABLE (amber) = right facts found, but one part was
    # identified indirectly -> a human glances at it.  FLAGGED = ask "say again".
    out["status"] = "FLAGGED" if problems else ("PROBABLE" if out["amber"] else "CONFIRMED")
    return out


# ---------------------------------------------------------------------------
# Second listen (Fix G, passed Experiment A2: rescued 5 calls in 4 of 6 voices, 0 wrong)
# ---------------------------------------------------------------------------
# Prisma's "transcribe" style sometimes glues "two niner" into "290". The SAME audio in
# "verbatim" style (words, no digit-writing) usually keeps "two niner". We ask again ONLY in
# that case, and accept the second answer only if it can't be a different runway:
#   - the first listen produced ONE glued runway number (3+ digits) and nothing else was wrong
#   - the second runway's digits are the START of the glued number (290 -> 29, never 290 -> 28)
#   - the side must match exactly (290R -> 29R only; 290 with no side never becomes 29R)
#   - the second runway exists at this airport, and the callsign is the same in both listens
# Result is always AMBER, never green.

# DEL_2023, 10 dB, noise recording 1 (4 Nov): listen 1 "ARF 725, runway 290, right" (callsign found by its number),
# listen 2 "ARF riven two five, runway two niner, right" - runway clear, but "seven" -> "riven" so NO callsign,
# and Fix G refused because the callsigns differ. A missing callsign is not a different one. Found on 1 clip:
# OFF until exp_a10 Part G (re-scores every saved transcript, no API) shows >=1 better, 0 worse, 0 new WRONG.
# A10 Part G (4 Nov): 15 saved transcripts with a second listen -> 0 better, 0 worse -> FAIL, stays OFF.
# (No harm found, but no help outside the one clip it came from: not enough to turn it on.)
FIXG_SILENT_CALLSIGN = False


def needs_second_listen(r):
    """True when the first result failed ONLY because the runway number was glued (e.g. 290)."""
    glued = re.search(r"RUNWAY\s+(\d{3,})([LRC]?)\b", r["normalized"].upper())
    return bool(glued) and r["problems"] == ["no runway heard"]


def second_listen(r1, second_text, airport, expected_traffic):
    if any(x.startswith("runway heard as") for x in r1["amber"]) and r1.get("raw") is not None:
        # Fix G (A17) read a glued runway from listen 1. If the second listen of the same audio names ANOTHER runway
        # or ANOTHER callsign, the audio is in doubt: undo G, and the rules below decide (they FLAG on disagreement).
        r2 = extract(second_text, airport, expected_traffic, glue=False)
        if (r2["runway"] and r2["runway"] != r1["runway"]) or \
                (r2["callsign"] and r1["callsign"] and r2["callsign"] != r1["callsign"]):
            r1 = extract(r1["raw"], airport, expected_traffic, glue=False)
    if not needs_second_listen(r1):
        return r1
    glued_digits, glued_side = re.search(r"RUNWAY\s+(\d{3,})([LRC]?)\b", r1["normalized"].upper()).groups()
    r2 = extract(second_text, airport, expected_traffic)
    rwy = r2["runway"]
    silent = FIXG_SILENT_CALLSIGN and r2["callsign"] is None      # listen 2 heard NO callsign: not a contradiction
    if rwy is None or (r2["callsign"] != r1["callsign"] and not silent):
        return r1
    digits, side = re.match(r"(\d+)([LRC]?)", rwy).groups()
    if not glued_digits.startswith(digits) or glued_side != side:   # side must match exactly, incl. 'no side'
        return r1
    out = dict(r1, runway=rwy, problems=[], status="PROBABLE")
    out["amber"] = r1["amber"] + [f"runway from second listen: first heard {glued_digits}{glued_side}, second heard {rwy}"]
    return out


# ---------------------------------------------------------------------------
# Fix N (LIVE: passed Experiment A3 on 31 Oct - 11 clips / 6 lines rescued, 0 WRONG): niner glue in FLIGHT numbers
# ---------------------------------------------------------------------------
# Dev run 31 Oct: "IFLY niner seven one four" came out as 90714 / 98714, "eight niner niner fife"
# as 89995 - the same "niner -> two digits" glue as runway 290. Flight numbers have at most
# 4 digits, so a 5+ digit number is impossible. Ask the same audio again in verbatim and accept
# its callsign only if it is the glued number with digits removed RIGHT AFTER a 9, the flight
# is on frequency, and the runway agrees in both listens. Always AMBER.
NINER_GLUE_FIX = True


def _niner_deletions(num):
    """Flight numbers (max 4 digits) you get from `num` by undoing the niner glue only:
    "niner" was written 90 / 99 / 98, so we may delete a 0, 9 or 8 that directly follows a kept 9."""
    found = set()

    def walk(i, kept):
        if i == len(num):
            if 1 <= len(kept) <= 4:
                found.add(kept)
            return
        walk(i + 1, kept + num[i])
        if kept.endswith("9") and num[i - 1] == "9" and num[i] in "098":
            walk(i + 1, kept)            # drop the glued extra digit

    walk(0, "")
    return found


def needs_callsign_second_listen(r):
    long_runs = re.findall(r"\d{5,}", r["normalized"])
    cs_only = r["problems"] and all("callsign" in p for p in r["problems"])
    return bool(long_runs) and cs_only and r["runway"] is not None


def callsign_second_listen(r1, second_text, airport, expected_traffic, force=False):
    if not (NINER_GLUE_FIX or force) or not needs_callsign_second_listen(r1):
        return r1
    r2 = extract(second_text, airport, expected_traffic)
    cs = r2["callsign"]
    if cs is None or r2["runway"] != r1["runway"] or cs not in expected_traffic:
        return r1
    digits = re.sub(r"\D", "", cs[3:])
    runs = re.findall(r"\d{5,}", r1["normalized"])
    if not any(digits in _niner_deletions(run) for run in runs):
        return r1
    out = dict(r1, callsign=cs, problems=[], status="PROBABLE")
    out["amber"] = r1["amber"] + r2["amber"] + [f"flight number from second listen: first heard {runs[0]}, second heard {cs}"]
    return out


# ---------------------------------------------------------------------------
# Vehicle check (LIVE: passed Experiment A4 part 2 on 31 Oct - caught the only wrong vehicle,
# 0 missed, 3 of 76 right calls not confirmed + 1 API error)
# ---------------------------------------------------------------------------
# Vehicle numbers are ONE digit. If another vehicle of the same kind is active, a single slip
# ("four" heard as "2") lands on a real vehicle and passes every other check (dev2 e000v).
# So the same audio is heard again in verbatim:
#   same vehicle number      -> unchanged
#   a DIFFERENT number       -> FLAG "heard Bird Chaser 2 and Bird Chaser 4 - say again"
#   no number / error        -> AMBER "second listen could not confirm" (never green)

def needs_vehicle_second_listen(r, expected_traffic):
    cs = r["callsign"]
    if not cs or cs[:3] in AIRLINES.values():
        return False
    kind = cs.rstrip("0123456789")
    return any(t != cs and t.rstrip("0123456789") == kind for t in expected_traffic)


def vehicle_second_listen(r1, second_text, airport, expected_traffic):
    if not needs_vehicle_second_listen(r1, expected_traffic):
        return r1
    r2 = extract(second_text, airport, expected_traffic)
    cs1, cs2 = r1["callsign"], r2["callsign"]
    if cs2 == cs1:
        return r1
    out = dict(r1, amber=list(r1["amber"]), problems=list(r1["problems"]))
    if cs2 and cs2.rstrip("0123456789") == cs1.rstrip("0123456789"):
        out["callsign"] = None
        out["problems"].append(f"vehicle number unclear: heard {cs1} and {cs2} - say again")
    else:
        why = "unavailable" if second_text.startswith("<error") else "could not confirm the vehicle number"
        out["amber"].append(f"second listen {why}: {cs1} not double-checked")
    out["status"] = "FLAGGED" if out["problems"] else "PROBABLE"
    return out
