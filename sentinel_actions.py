"""
Sentinel-V Step 1 — WHAT is each runway being used for, and by whom?

analyse(text, airport, traffic, channel, phases) returns the Step-0 parse (runway, callsign,
status) PLUS one entry per runway mentioned:
    {"runway", "valid", "action", "strength", "conflict", "cues"}

Actions
  LAND, TAKEOFF, LINEUP, CROSS            -> will be ON that runway
  HOLD_SHORT, TAXI_HP                     -> must STOP before that runway
  GO_AROUND, STOP                         -> leaving it / stop now
  REQ_CROSS, REQ_ENTER                    -> a VEHICLE asking to go on it (not cleared yet)
  REPORT_BIRDS                            -> a vehicle reporting birds on it
  None                                    -> no instruction heard (shown amber, treated as "maybe on it")

Strong cue = ICAO Doc 4444 phrase heard in full ("cleared to land", "hold short").
Weak cue   = only the END of the phrase survived ("... to land", "... short runway", "... and wait").
             Why the end: push-to-talk clips the FIRST syllables (dev runs: "Taking short",
             "I love and wait", "Request to land"). Weak cue -> AMBER, never green.

Safety rules
  - two different instructions for one runway  -> FLAG (e.g. "Crossing short runway")
  - instruction impossible for the aircraft's state (ADS-B air/ground bit):
      LAND / GO_AROUND need an airborne aircraft; TAKEOFF / LINEUP / CROSS / HOLD_SHORT need one
      on the ground -> FLAG. Catches "cleared to land" heard as "cleared for takeoff" (dev2 e012a, e017a).
  - on the vehicle (airside) channel a vehicle never GIVES clearances: "cross runway" from a
    vehicle is a request, and "hold short / holding point Bravo" is where it is waiting.
  - every runway mentioned must exist at the airport (a 2-runway call checks both).
"""
import re
from sentinel_parse import (extract, normalize, AIRPORTS, second_listen, callsign_second_listen,
                            vehicle_second_listen)

STRONG = [
    ("LAND",       r"\bCLEARED\s+TO\s+LAND\b"),
    ("TAKEOFF",    r"\bCLEARED\s+FOR\s+TAKE\s*-?\s*OFF\b"),
    ("LINEUP",     r"\bLINE\s+UP(\s+AND\s+WAIT)?\b"),
    ("CROSS",      r"\bCROSS(ING)?\s+RUNWAY\b"),
    ("HOLD_SHORT", r"\bHOLD(ING)?\s+SHORT\b"),
    ("TAXI_HP",    r"\bTAXI\s+TO\s+HOLDING\s+POINT\b"),
    ("GO_AROUND",  r"\bGO(ING)?\s+AROUND\b"),
    ("STOP",       r"\bSTOP\s+IMMEDIATELY\b|\bCANCEL\s+TAKE\s*-?\s*OFF\b|\bHOLD\s+POSITION\b|\bSTOPPING\b"),
]
WEAK = [
    # kept only if seen in 2+ voices and never for a different instruction (dev + dev2, 600 clips).
    # Dropped by that rule: "for land" (1 voice), "for takeoff" (1 voice) -> those stay "not heard".
    ("LAND",       r"\bTO\s+LAND\b|\bLAND\s+RUNWAY\b"),
    ("LINEUP",     r"\bAND\s+WAIT\b"),
    ("HOLD_SHORT", r"\bSHORT\s+(OF\s+)?RUNWAY\b"),
    ("CROSS",      r"\bCROSS(ING)?\b"),                    # lets "Crossing short runway" become a conflict
]
VEHICLE = [   # airside channel: Hinglish / Hindi / Marathi (no \b after Devanagari: matras break it)
    ("REQ_CROSS",    r"\bCROSS\b|क्रॉस|ओलांड"),
    ("REQ_ENTER",    r"\bENTER\b|एंटर|(\bFOD\b|एफओडी|एफ़\s*ओ\s*डी|फॉड)"),
    ("REPORT_BIRDS", r"पक्षी|\bPAKSHI\b|\bBIRDS\b"),
]
# English "BIRDS" fired once on a garbled STATION NAME: "4 birds is a 5 runway 27" = "Bird Chaser 5" (A10, 4 Nov;
# 1 false bird in 295 saved vehicle transcripts). The word "bird" is in the station's own name, so in English it
# can mean the hazard OR the speaker. Strict rule: English "birds" is the hazard only when
#   (a) a hazard word follows it: birds ON / NEAR / AT / OVER / ACROSS / REPORTED / SPOTTED / SIGHTED,
#       or "bird activity", or
#   (b) the station already named itself before it ("Bird Chaser 2, ... birds")
# Marathi/Hindi पक्षी is never the station name, so it is untouched.
# A11 (4 Nov, rule fixed before): 30 new English lines x 3 noise levels + 295 saved transcripts = 385:
#   0 true birds lost, 0 false birds, 51/54 English bird clips shown, +18 'bird activity' reports the old cue missed.
#   The 3 not shown: 2x singular 'bird on runway' (1 voice: not added), 1 with no runway number heard. -> ON
BIRDS_EN_STRICT = True
EN_BIRDS_HAZARD = re.compile(r"\bBIRDS\b(?=[\s,]+(ON|NEAR|AT|OVER|ACROSS|REPORTED|SPOTTED|SIGHTED)\b)|\bBIRD\s+ACTIVITY\b")
STATION_NAME = re.compile(r"\bBIRD\s+CHASER\b|\bFOLLOW\s+ME\b")


def _birds_ok(up, start, cue):
    """Strict mode: is this English 'birds' the hazard (not the station's garbled name)?"""
    if not re.fullmatch(r"BIRDS|BIRD\s+ACTIVITY", cue):
        return True                                   # पक्षी / PAKSHI: never the station name
    if any(m.start() == start for m in EN_BIRDS_HAZARD.finditer(up)):
        return True
    st = STATION_NAME.search(up)
    return bool(st) and st.end() <= start
# call-level weak cue: "Going around" readback with "Go" clipped -> "Heading/Flying around", "Around"
# (step1 run: 11 times, 2 voices, never in 600 dev/dev2 clips). "go round" (1 voice) not added.
WEAK_CALL = [("GO_AROUND", r"\bAROUND\b")]
# Experiment A7 decides this (3 Nov): OFF until it passes its rule.
INSTRUCTION_SECOND_LISTEN = False


def needs_instruction_second_listen(normalized, airport, channel):
    """A runway that exists was named, but no instruction was heard for it."""
    return any(x["valid"] and x["action"] is None and not x["conflict"]
               for x in instructions(normalized, airport, channel))


CONDITIONAL = r"\bBEHIND\b|\bAFTER\s+THE\s+(LANDING|DEPARTING)\b"
NEEDS_AIR = {"LAND", "GO_AROUND"}
NEEDS_GROUND = {"TAKEOFF", "LINEUP", "CROSS", "HOLD_SHORT", "TAXI_HP"}
ON_RUNWAY = {"LAND", "TAKEOFF", "LINEUP", "CROSS", "REQ_CROSS", "REQ_ENTER", None}

RUNWAY_RE = re.compile(r"\bRUNWAY\s+(\d{1,2}[LRC]?)\b")


def _hits(up, table, strength):
    return [(m.start(), a, m.group(0), strength) for a, pat in table for m in re.finditer(pat, up)]


def instructions(normalized, airport, channel="tower"):
    up = normalized.upper()
    mentions = [(m.start(), m.end(), m.group(1)) for m in RUNWAY_RE.finditer(up)]
    if channel == "airside":
        table = VEHICLE
        if BIRDS_EN_STRICT:
            table = VEHICLE[:-1] + [("REPORT_BIRDS", r"पक्षी|\bPAKSHI\b|\bBIRDS\b|\bBIRD\s+ACTIVITY\b")]
        hits = _hits(up, table, "strong")
        if BIRDS_EN_STRICT:
            hits = [h for h in hits if h[1] != "REPORT_BIRDS" or _birds_ok(up, h[0], h[2])]
    else:
        hits = _hits(up, STRONG, "strong") + _hits(up, WEAK, "weak")
    out = []
    for i, (s, e, rw) in enumerate(mentions):
        lo = mentions[i - 1][1] if i else 0
        hi = mentions[i + 1][0] if i + 1 < len(mentions) else len(up)
        mine = [h for h in hits if lo <= h[0] < hi and h[1] not in ("GO_AROUND", "STOP")]
        if len(mentions) > 1:
            mine = [h for h in mine if h[0] < s or i + 1 == len(mentions)]
        acts = {a for _, a, _, _ in mine}
        if channel == "airside" and len(acts) > 1:
            # "FOD check ke liye enter karna hai" = one request; "birds" report wins over nothing else
            acts = {"REQ_ENTER"} if "REQ_ENTER" in acts and "REQ_CROSS" not in acts else acts
        strength = None
        if len(acts) == 1:
            a = next(iter(acts))
            strength = "strong" if any(h[1] == a and h[3] == "strong" for h in mine) else "weak"
        valid = len(re.sub(r"\D", "", rw)) == 2 and rw in AIRPORTS[airport]["runways"]
        out.append({"runway": rw, "valid": valid, "action": next(iter(acts)) if len(acts) == 1 else None,
                    "strength": strength, "conflict": len(acts) > 1,
                    "cues": [c for _, _, c, _ in sorted(mine)]})
    return out


# "Runway" clipped by push-to-talk and heard as "Taxiway": "Taxiway 28, cleared for takeoff". Seen in 4 voices
# (dev d003b Prakash, d020b Avinash, dev2 e003b Harshad, scenario p1 Riyaa: 23 transcripts), the speaker said
# "runway" every time, and EVERY time the call was a runway-only clearance. Indian taxiways are lettered
# (Bravo, Charlie, B4) - "taxiway 28 ... cleared for takeoff" cannot be a taxiway. So, tower/pilot calls only,
# no "runway" word in the call, a number right after "taxiway", and cleared for takeoff / to land / line up:
# read it as runway. Always amber. (Project rule for word mappings: 2+ voices, never a wrong result - checked
# by the free re-score in exp_a12 before it counts.)
# A12 (4 Nov, free re-score, rule fixed before): 720 saved tower/pilot transcripts -> 0 worse, 0 new WRONG, but
# 0 better (the 3 dev lines with "Taxiway 28..." had ALSO lost the callsign, so they stay FLAG) -> rule T1 FAIL -> OFF.
# Its own test now: NEW noise recordings 5-9 of the scenarios (exp_a12.py --taxiway), rule in exp_a12.py.
TAXIWAY_AS_RUNWAY = False
_NUMW = r"(?:\d|zero|one|two|three|tree|four|five|fife|six|seven|eight|nine|niner)"
_TAXIWAY_NUM = re.compile(r"\btaxi\s*way\b(?=[\s,]*" + _NUMW + r")", re.IGNORECASE)
_RUNWAY_ONLY = re.compile(r"\bcleared\s+(for\s+take\s*-?\s*off|to\s+land)\b|\bline\s+up\b", re.IGNORECASE)


# Other sound-alikes of a clipped "Runway" seen 4-5 Nov: "One way 27" / "1 way, 2 niner right" (Riyaa only so far),
# "Airway 10" (Riyaa only). Each is OFF until Experiment A13 shows it in 2+ voices and the free re-scores pass.
RUNWAY_SOUNDALIKES = {"taxiway": r"taxi\s*way", "one way": r"(?:one|1)\s*way", "airway": r"air\s*way"}
# A13 (5 Nov, 6 voices x clean/10/5 dB, rule fixed before): 'taxiway' 0 voices, 'one way' 1 voice (Riyaa again),
# 'airway' 0 -> all FAIL rule W1 -> OFF. What a lost "Runway" really turns into: a digit glued to the runway number
# ("227", "2827", "927" for "runway 27") in 15 of 24 noisy readbacks - filling it from the tower's runway would be
# circular (Fix C, rejected), so it stays AMBER "runway not read back clearly".
RUNWAY_SOUNDALIKES_ON = set()


def _taxiway_as_runway(text, channel):
    on = set(RUNWAY_SOUNDALIKES_ON) | ({"taxiway"} if TAXIWAY_AS_RUNWAY else set())
    if not on or channel == "airside" or not text or re.search(r"\brunway\b", text, re.IGNORECASE) \
            or not _RUNWAY_ONLY.search(text):
        return text, False
    for w in sorted(on):
        pat = re.compile(r"\b" + RUNWAY_SOUNDALIKES[w] + r"\b(?=[\s,]*" + _NUMW + r")", re.IGNORECASE)
        if pat.search(text):
            return pat.sub("runway", text, count=1), True
    return text, False


def analyse(text, airport, traffic, channel="tower", phases=None, second_text=None):
    """Step-0 parse (+ second listens) + Step-1 instructions.
    phases: {callsign: "air" | "ground"} from ADS-B, optional."""
    traffic = set(traffic)
    text, taxi = _taxiway_as_runway(text, channel)
    if second_text is not None:
        second_text, _ = _taxiway_as_runway(second_text, channel)
    r = extract(text, airport, traffic)
    if taxi:
        r = dict(r, amber=r["amber"] + ["'runway' heard as 'taxiway' (a numbered runway-only clearance) - read as runway"])
    if second_text is not None:
        r = vehicle_second_listen(callsign_second_listen(second_listen(r, second_text, airport, traffic),
                                                         second_text, airport, traffic),
                                  second_text, airport, traffic)
    # if the runway came from the second listen, read the instructions from that listen too
    src = normalize(second_text) if any("runway from second listen" in a for a in r["amber"]) else r["normalized"]
    ins = instructions(src, airport, channel)
    problems, amber = list(r["problems"]), list(r["amber"])
    if INSTRUCTION_SECOND_LISTEN and second_text is not None:
        # a runway was heard but its instruction was not (push-to-talk ate "Crossing"/"Holding").
        # The verbatim listen of the SAME audio (no tower context, so not circular) may still have it.
        # It may only FILL an empty instruction, never change one, and is always amber.
        ins2 = {x["runway"]: x for x in instructions(normalize(second_text), airport, channel)}
        for x in ins:
            y = ins2.get(x["runway"])
            if x["action"] is None and x["valid"] and y and y["action"] and not y["conflict"]:
                x.update(action=y["action"], strength="weak", cues=y["cues"])
                amber.append(f"runway {x['runway']}: instruction only in the second listen ({y['action']})")
    seen = {}
    for x in ins:
        seen.setdefault(x["runway"], set()).add(x["action"])
    for rw, a in seen.items():
        if len(a) > 1:
            # step1 s012b: "cross 29R, hold short 29L" heard as "Ascend runway 29 left, holding short runway 29 left"
            problems.append(f"runway {rw} named twice with different instructions - say again")
    for x in ins:
        if x["conflict"]:
            problems.append(f"runway {x['runway']}: two different instructions heard ({', '.join(x['cues'])}) - say again")
        elif x["action"] is None:
            amber.append(f"runway {x['runway']}: instruction not heard")
        elif x["strength"] == "weak":
            amber.append(f"runway {x['runway']}: instruction partly heard ('{x['cues'][-1].lower()}') - {x['action']}")
        if len(ins) > 1 and not x["valid"]:
            problems.append(f"runway {x['runway']} does not exist at {AIRPORTS[airport]['name']}")
    if re.search(CONDITIONAL, r["normalized"].upper()):
        amber.append("conditional clearance (behind / after traffic)")
    phase = (phases or {}).get(r["callsign"])
    for x in ins:
        a = x["action"]
        if phase == "ground" and a in NEEDS_AIR or phase == "air" and a in NEEDS_GROUND:
            problems.append(f"{a} does not fit {r['callsign']} ({'on the ground' if phase == 'ground' else 'airborne'}) - say again")
    # instructions that need no runway number: "go around", "stop immediately", "cancel take-off"
    call_actions = sorted({a for _, a, _, _ in _hits(r["normalized"].upper(), STRONG, "strong")
                           if a in ("GO_AROUND", "STOP")}) if channel != "airside" else []
    if channel != "airside" and not call_actions:
        weak_calls = sorted({a for _, a, _, _ in _hits(r["normalized"].upper(), WEAK_CALL, "weak")})
        if weak_calls and not ins:
            call_actions = weak_calls
            amber.append(f"instruction partly heard: {', '.join(weak_calls)}")
    if call_actions and not ins:
        problems = [p for p in problems if p != "no runway heard"]     # "go around" carries no runway
    out = dict(r, instructions=ins, call_actions=call_actions, problems=problems, amber=amber)
    out["status"] = "FLAGGED" if problems else ("PROBABLE" if amber else "CONFIRMED")
    return out



# Fix C ("context listen": re-hear a flagged readback with the tower's call as previous_text and
# fill the gaps) was REJECTED on 1 Nov before spending any API calls. Worst-case test on 129 flagged
# readbacks (listen 2 = the tower's words exactly, i.e. Prisma fully biased by context):
#   rescued 39, but HID 4 deliberate wrong readbacks:
#     d004b  pilot said 9093 (tower 9091), heard "909"   -> completed to 9091   (lost digit = the error)
#     d013b  pilot said 9404 (tower 9494), heard "I flew by niner 404" -> filled 9494
#     e010b  pilot read back the wrong runway, heard "3C" / "3 runways in 2" -> filled the tower's 27  (x2)
# Root cause: anything filled from the tower's words can no longer be checked AGAINST the tower's
# words - it is circular. Step 2 instead shows what is missing ("callsign 775_ incomplete") and asks.
