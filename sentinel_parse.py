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
    "nine": "9", "niner": "9", "nayana": "9", "liner": "9", "minor": "9",
    "ज़ीरो": "0", "झिरो": "0", "जीरो": "0", "वन": "1", "टू": "2", "थ्री": "3", "फोर": "4",
    "फाइव": "5", "फाईव्ह": "5", "सिक्स": "6", "सेवन": "7", "सेव्हन": "7", "एट": "8",
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


def normalize(text):
    t = text
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


def extract(text, airport, expected_traffic):
    """
    expected_traffic: callsigns known to be on frequency (from schedule/ADS-B), e.g. {"IGO6053"}
    Returns dict with runway, callsign and a list of problems.
    """
    norm = normalize(text)
    up = norm.upper()
    problems, out = [], {"normalized": norm, "runway": None, "callsign": None,
                         "corrected": False, "suggestion": None}

    m = re.search(r"RUNWAY\s+(\d{1,2}[LRC]?)\b", up)
    if not m:
        problems.append("no runway heard")
    else:
        digits, side = re.match(r"(\d+)([LRC]?)", m.group(1)).groups()
        rwy = digits.zfill(2) + side            # "9R" -> "09R", "27" -> "27"
        if rwy in AIRPORTS[airport]["runways"]:
            out["runway"] = rwy
        else:
            problems.append(f"runway {rwy} does not exist at {AIRPORTS[airport]['name']}")

    for word, code in VEHICLES.items():
        if word in up:
            vm = re.search(word + r"\W*(\d+)", up)
            if not vm:
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
            problems.append("no callsign heard")

    out["problems"] = problems
    out["status"] = "CONFIRMED" if not problems else "FLAGGED"
    return out
