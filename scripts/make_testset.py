"""
Builds test sets from templates (fixes problems #17 and #18).

  dev     : 60 lines, fixed seed. We are ALLOWED to look at these and fix the code.
  locked  : 150 lines, random seed. Run ONCE on frozen code. Never used for fixing.
            Uses voices that our fixes never saw (Timbre v2.5 English + Hindi voices).
  human   : 30 lines for real people to read aloud, with a printable recording sheet.

Every line stores:
  text        what is spoken (fed to Timbre, or read by a human)
  ideal       what a PERFECT transcription would look like (used to self-check the parser)
  truth       runway + callsign actually SPOKEN (for a wrong readback, the wrong value)
  traffic     who is on frequency (sometimes includes a look-alike callsign on purpose)
  traps       tags: similar_callsign, wrong_readback_runway, wrong_readback_side,
                    wrong_readback_callsign, icao_digits

Usage:
  python scripts/make_testset.py dev
  python scripts/make_testset.py dev2     (fresh sentences, same voices: checks fixes made on dev)
  python scripts/make_testset.py step1    (Step 1 phrases: two runways, taxi, conditional, go around, stop, wind)
  python scripts/make_testset.py locked
  python scripts/make_testset.py human
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
import random
import secrets

from sentinel_parse import AIRPORTS

AIRLINES = {"IGO": "IFLY", "AIC": "Air India", "AKJ": "Akasa Air"}
DIGIT_STYLES = {
    "plain": {"3": "three", "5": "five", "9": "nine"},
    "icao": {"3": "tree", "5": "fife", "9": "niner"},     # real ICAO radio pronunciation
    "niner": {"9": "niner"},                               # most common in Indian ATC
}
BASE_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
              "6": "six", "7": "seven", "8": "eight", "9": "nine"}
SIDE_EN = {"L": "left", "R": "right", "C": "centre"}
DEV_DIGITS = {"0": "ज़ीरो", "1": "वन", "2": "टू", "3": "थ्री", "4": "फोर", "5": "फाइव",
              "6": "सिक्स", "7": "सेवन", "8": "एट", "9": "नाइन"}
SIDE_DEV = {"L": "लेफ्ट", "R": "राइट"}

V3_DEV = ["Avinash", "Riyaa", "Harshad", "Prakash", "Devansh", "Shubham"]
VOICES = {
    "dev": {"en": [(v, "timbre-v3.0", "en-IN") for v in V3_DEV],
            "hi": [(v, "timbre-v3.0", "hi-IN") for v in V3_DEV],
            "mr": [("Zahira", "timbre-v2.5", "mr-IN")],
            "hinglish": [("Poorvi", "timbre-v2.5", "hi-en")]},
    # never used in any test so far -> nothing was tuned on them
    "locked": {"en": [(v, "timbre-v2.5", "en-IN") for v in
                      ["Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish"]],
               "hi": [(v, "timbre-v2.5", "hi-IN") for v in
                      ["Nalini", "Bhavna", "Deepak", "Roopesh", "Vikrant", "Omkar", "Urmila"]],
               "mr": [("Ishaan", "timbre-v2.5", "mr-IN")],
               "hinglish": [("Poorvi", "timbre-v2.5", "hi-en")]},   # only Hinglish voice that exists
}

ACTIONS = {
    "land": ("{cs}, runway {rw}, cleared to land.", "Cleared to land runway {rw}, {cs}."),
    "takeoff": ("{cs}, runway {rw}, cleared for takeoff.", "Runway {rw}, cleared for takeoff, {cs}."),
    "lineup": ("{cs}, line up and wait runway {rw}.", "Line up and wait runway {rw}, {cs}."),
    "cross": ("{cs}, cross runway {rw}, report vacated.", "Crossing runway {rw}, {cs}."),
    "hold": ("{cs}, hold short runway {rw}.", "Holding short runway {rw}, {cs}."),
}


def say_digits(s, style):
    words = {**BASE_WORDS, **DIGIT_STYLES[style]}
    return " ".join(words[c] for c in s)


def say_runway(rw, style):
    d, side = rw.rstrip("LRC"), rw[len(rw.rstrip("LRC")):]
    return say_digits(d, style) + (f" {SIDE_EN[side]}" if side else "")


def callsign(rng):
    code = rng.choice(list(AIRLINES))
    num = str(rng.randint(100, 9999))
    return code + num


def lookalike(cs, rng):
    code, num = cs[:3], list(cs[3:])
    if len(num) >= 2 and rng.random() < 0.6:
        i = rng.randrange(len(num) - 1)
        num[i], num[i + 1] = num[i + 1], num[i]          # 2817 -> 2871
    else:
        i = rng.randrange(len(num))
        num[i] = rng.choice([d for d in "0123456789" if d != num[i]])
    out = code + "".join(num)
    return out if out != cs and not out[3] == "0" else None


def say_callsign(cs, style):
    return f"{AIRLINES[cs[:3]]} {say_digits(cs[3:], style)}"


def ideal_callsign(cs):
    return f"{AIRLINES[cs[:3]]} {cs[3:]}"


def flight_lines(rng, kind, idx):
    ap = rng.choice(list(AIRPORTS))
    runways = sorted(AIRPORTS[ap]["runways"])
    rw = rng.choice(runways)
    cs = callsign(rng)
    traffic = {cs} | {callsign(rng) for _ in range(3)}
    traps = []
    if rng.random() < 0.4:
        la = lookalike(cs, rng)
        if la:
            traffic.add(la)
            traps.append("similar_callsign")
    style = rng.choices(list(DIGIT_STYLES), weights=[3, 2, 5])[0]
    if style == "icao":
        traps.append("icao_digits")
    action = rng.choice(list(ACTIONS))
    tower_t, pilot_t = ACTIONS[action]
    voices = VOICES[kind]["en"]

    items = []
    tv = rng.choice(voices)
    items.append(dict(
        id=f"{kind[0]}{idx:03d}a", channel="tower", airport=ap, action=action,
        voice=tv[0], tts_model=tv[1], tts_lang=tv[2],
        text=tower_t.format(cs=say_callsign(cs, style), rw=say_runway(rw, style)),
        ideal=tower_t.format(cs=ideal_callsign(cs), rw=rw),
        truth={"runway": rw, "callsign": cs}, traffic=sorted(traffic), traps=list(traps)))

    # pilot readback, 25% with a deliberate mistake (truth = what the pilot SAYS)
    p_rw, p_cs, p_traps = rw, cs, list(traps)
    if rng.random() < 0.25:
        err = rng.choice(["runway", "side", "callsign"])
        side_flip = rw[:-1] + {"L": "R", "R": "L"}.get(rw[-1], "") if rw[-1] in "LR" else None
        if err == "side" and side_flip in AIRPORTS[ap]["runways"]:
            p_rw = side_flip; p_traps.append("wrong_readback_side")
        elif err in ("runway", "side"):
            p_rw = rng.choice([r for r in runways if r != rw]); p_traps.append("wrong_readback_runway")
        else:
            bad = None
            while not bad or bad in traffic:
                bad = lookalike(cs, rng)
            p_cs = bad; p_traps.append("wrong_readback_callsign")
    pv = rng.choice([v for v in voices if v != tv] or voices)
    items.append(dict(
        id=f"{kind[0]}{idx:03d}b", channel="pilot", airport=ap, action=action, readback_of=items[0]["id"],
        voice=pv[0], tts_model=pv[1], tts_lang=pv[2],
        text=pilot_t.format(cs=say_callsign(p_cs, style), rw=say_runway(p_rw, style)),
        ideal=pilot_t.format(cs=ideal_callsign(p_cs), rw=p_rw),
        truth={"runway": p_rw, "callsign": p_cs}, traffic=sorted(traffic), traps=p_traps))
    return items


VEH = {"FOLLOWME": ("Follow Me", "फॉलो मी"), "BIRDCHASER": ("Bird Chaser", "बर्ड चेसर")}


def airside_line(rng, kind, idx):
    ap = rng.choice(list(AIRPORTS))
    rw = rng.choice(sorted(AIRPORTS[ap]["runways"]))
    vtype = rng.choice(list(VEH))
    n = str(rng.randint(1, 5))
    others = {vtype + str(k) for k in range(1, 6) if str(k) != n and rng.random() < 0.4}
    traffic = sorted({vtype + n} | others | {callsign(rng)})
    en, dv = VEH[vtype]
    d, side = rw.rstrip("LRC"), rw[len(rw.rstrip("LRC")):]
    rw_dev = " ".join(DEV_DIGITS[c] for c in d) + (f" {SIDE_DEV[side]}" if side else "")
    rw_rom = " ".join(BASE_WORDS[c] for c in d) + (f" {SIDE_EN[side]}" if side else "")
    lang = rng.choice(["hi", "mr", "hinglish"])
    if lang == "hi":
        text, roman = rng.choice([
            (f"टावर, {dv} {DEV_DIGITS[n]}, रनवे {rw_dev} क्रॉस करना है, होल्डिंग पॉइंट ब्रावो पर हूँ।",
             f"Tower, {en} {BASE_WORDS[n]}, runway {rw_rom} cross karna hai, holding point Bravo par hoon."),
            (f"टावर, {dv} {DEV_DIGITS[n]}, रनवे {rw_dev} पर एफ़ ओ डी चेक के लिए जाना है, परमिशन चाहिए।",
             f"Tower, {en} {BASE_WORDS[n]}, runway {rw_rom} par FOD check ke liye jaana hai, permission chahiye."),
        ])
    elif lang == "mr":
        text, roman = rng.choice([
            (f"टॉवर, {dv} {DEV_DIGITS[n]}, रनवे {rw_dev} वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय.",
             f"Tower, {en} {BASE_WORDS[n]}, runway {rw_rom} var pakshi aahet, mi taxiway Charlie javal thamblo aahe."),
            (f"टॉवर, {dv} {DEV_DIGITS[n]}, मला रनवे {rw_dev} ओलांडायचा आहे, परवानगी द्या.",
             f"Tower, {en} {BASE_WORDS[n]}, mala runway {rw_rom} olandaycha aahe, parvangi dya."),
        ])
    else:
        roman = rng.choice([
            f"Tower, {en} {BASE_WORDS[n]}, runway {rw_rom} pe FOD check ke liye enter karna hai, permission chahiye.",
            f"Tower, {en} {BASE_WORDS[n]}, runway {rw_rom} cross karna hai, Bravo pe hold kar raha hoon.",
        ])
        text = roman
    v = rng.choice(VOICES[kind]["mr" if lang == "mr" else "hinglish" if lang == "hinglish" else "hi"])
    return dict(id=f"{kind[0]}{idx:03d}v", channel="airside", airport=ap, action="vehicle", lang=lang,
                voice=v[0], tts_model=v[1], tts_lang=v[2], text=text, roman=roman,
                ideal=f"Tower, {en} {n}, runway {rw}.",
                truth={"runway": rw, "callsign": vtype + n}, traffic=traffic, traps=[])



# ---------------------------------------------------------------------------
# Step 1 phrases (ICAO Doc 4444 forms): two runways in one call, taxi to holding point,
# conditional line-up, go around, stop, wind numbers next to a runway.
# truth["instructions"] = [[runway, action], ...] in spoken order; truth["call_actions"] for
# instructions that carry no runway; phase = the aircraft's ADS-B air/ground state.
# ---------------------------------------------------------------------------
# Delhi: the parallel runways 29L/29R (Aug 2023: VTI926 crossing 29R while VTI725 took off from it).
# Mumbai: 09/27 and 14/32 cross each other.
TWO_RUNWAYS = {"VIDP": [("29R", "29L"), ("29L", "29R"), ("11R", "11L")], "VABB": [("27", "32"), ("14", "09")]}

STEP1 = {
    "two_runways": ("{cs}, cross runway {r1}, hold short runway {r2}.",
                    "Crossing runway {r1}, holding short runway {r2}, {cs}.",
                    lambda r1, r2: [[r1, "CROSS"], [r2, "HOLD_SHORT"]], [], False, "ground"),
    "taxi_hp":     ("{cs}, taxi to holding point runway {r1} via Bravo.",
                    "Taxi to holding point runway {r1} via Bravo, {cs}.",
                    lambda r1, r2: [[r1, "TAXI_HP"]], [], False, "ground"),
    "conditional": ("{cs}, behind the landing Airbus, line up and wait runway {r1}, behind.",
                    "Behind the landing Airbus, line up and wait runway {r1}, behind, {cs}.",
                    lambda r1, r2: [[r1, "LINEUP"]], [], True, "ground"),
    "go_around":   ("{cs}, go around, I say again, go around.",
                    "Going around, {cs}.",
                    lambda r1, r2: [], ["GO_AROUND"], False, "air"),
    "stop":        ("{cs}, stop immediately, I say again, stop immediately.",
                    "Stopping, {cs}.",
                    lambda r1, r2: [], ["STOP"], False, "ground"),
    "wind_land":   ("{cs}, wind {wind} degrees, one two knots, runway {r1}, cleared to land.",
                    "Cleared to land runway {r1}, {cs}.",
                    lambda r1, r2: [[r1, "LAND"]], [], False, "air"),
}


def step1_lines(rng, kind, idx, ptype):
    ap = rng.choice(list(TWO_RUNWAYS)) if ptype == "two_runways" else rng.choice(list(AIRPORTS))
    r1, r2 = rng.choice(TWO_RUNWAYS[ap]) if ptype == "two_runways" else (rng.choice(sorted(AIRPORTS[ap]["runways"])), None)
    cs = callsign(rng)
    traffic = sorted({cs} | {callsign(rng) for _ in range(3)})
    style = rng.choices(list(DIGIT_STYLES), weights=[3, 2, 5])[0]
    wind = rng.choice(["270", "090", "280", "100"])            # wind numbers that look like runways
    tower_t, pilot_t, ins, calls, cond, phase = STEP1[ptype]
    voices = VOICES[kind]["en"]
    tv = rng.choice(voices)
    pv = rng.choice([v for v in voices if v != tv])
    fmt = dict(cs=say_callsign(cs, style), r1=say_runway(r1, style), r2=say_runway(r2, style) if r2 else "",
               wind=say_digits(wind, style))
    ideal = dict(cs=ideal_callsign(cs), r1=r1, r2=r2 or "", wind=wind)
    truth = {"runway": r1 if ins(r1, r2) else None, "callsign": cs, "instructions": ins(r1, r2),
             "call_actions": calls, "conditional": cond}
    traps = [f"step1_{ptype}"] + (["icao_digits"] if style == "icao" else [])
    out = []
    for sfx, ch, tmpl, v in (("a", "tower", tower_t, tv), ("b", "pilot", pilot_t, pv)):
        out.append(dict(id=f"s{idx:03d}{sfx}", channel=ch, airport=ap, action=ptype, phase={cs: phase},
                        voice=v[0], tts_model=v[1], tts_lang=v[2],
                        text=tmpl.format(**fmt), ideal=tmpl.format(**ideal),
                        truth=dict(truth, conditional=cond and ch == "tower" or cond),
                        traffic=traffic, traps=list(traps)))
    return out


def build_step1(kind, seed, per_type):
    rng = random.Random(seed)
    items, idx = [], 0
    for _ in range(per_type):
        for ptype in STEP1:
            items += step1_lines(rng, kind, idx, ptype)
            idx += 1
    return items

def build(kind, seed, n_pairs, n_airside):
    rng = random.Random(seed)
    items = []
    for i in range(n_pairs):
        items += flight_lines(rng, "dev" if kind == "dev" else "locked", i)
    for i in range(n_airside):
        items.append(airside_line(rng, "dev" if kind == "dev" else "locked", i))
    return items


def build_human(seed):
    """30 lines for real people (5 Nov): the old sheet had only land/takeoff/cross/vehicle lines. Now it also has
    the Step-1 phrases and the Marathi bird reports, so friends' voices test everything the engine does.
      16 = 8 tower call + pilot readback pairs (some readbacks deliberately wrong, as in dev)
       6 = 3 Step-1 pairs: two runways in one call, go around, "behind the landing Airbus"
       8 = vehicle calls: 3 Marathi bird reports, 2 Marathi crossing requests, 2 Hindi, 1 Hinglish"""
    rng = random.Random(seed)
    items, idx, wrong = [], 0, 0
    while idx < 8:
        pair = flight_lines(rng, "locked", idx)
        is_wrong = any(t.startswith("wrong_readback") for it in pair for t in it["traps"])
        # content rule (decided before any recording): at least 3 of the 8 pairs have a deliberately wrong readback
        if not is_wrong and (8 - idx) <= (3 - wrong):
            continue
        wrong += is_wrong
        for it in pair:
            it["id"] = f"h{idx:03d}{it['id'][-1]}"
            items.append(it)
        idx += 1
    for ptype in ("two_runways", "go_around", "conditional"):
        for it in step1_lines(rng, "locked", idx, ptype):
            it["id"] = f"h{idx:03d}{it['id'][-1]}"
            items.append(it)
        idx += 1
    want = [("mr", "birds")] * 3 + [("mr", "cross")] * 2 + [("hi", "any")] * 2 + [("hinglish", "any")]
    for lang, what in want:
        while True:
            it = airside_line(rng, "locked", idx)
            rom = it["roman"].lower()
            if it["lang"] == lang and (what == "any" or (what == "birds") == ("pakshi" in rom)):
                break
        it["id"] = f"h{idx:03d}v"
        items.append(it)
        idx += 1
    return items


def recording_sheet(items, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Recording sheet\n\n"
                "Read each line like a real radio call: normal speed, numbers one digit at a time.\n"
                "Save each as  <yourname>_<id>.m4a  (example: sanoer_h003a.m4a) in the my_voice/ folder.\n"
                "Background sound (fan, traffic) is fine.\n"
                "Some lines contain DELIBERATE mistakes (a pilot reading back the wrong number). "
                "Read exactly what is written, do not correct it.\n\n| id | read this |\n|---|---|\n")
        for it in items:
            line = it["text"] if it.get("roman", it["text"]) == it["text"] else f"{it['text']}<br>({it['roman']})"
            f.write(f"| {it['id']} | {line} |\n")
        f.write("\nConsent: by sending these recordings you agree they are used only to test Sentinel-V on this laptop. "
                "They are never uploaded or published.\n")


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "dev"
    os.makedirs("testsets", exist_ok=True)
    if kind == "dev":
        seed, items, name = 1, build("dev", 1, 24, 12), "dev"
    elif kind == "dev2":
        # fresh sentences, same dev voices: checks fixes made on dev without touching the locked set.
        # Seed 25 = first seed (counting up from 2) that has all 5 trap kinds AND 10+ "niner" lines,
        # chosen from the sentence content only, before any audio was made.
        seed, items, name = 25, build("dev", 25, 24, 12), "dev2"
        for it in items:
            it["id"] = "e" + it["id"][1:]
    elif kind == "step1":
        seed, items, name = 101, build_step1("dev", 101, 4), "step1"
    elif kind == "locked":
        seed = secrets.randbits(32)
        items, name = build("locked", seed, 60, 30), f"locked_{seed:08x}"
        items += build_step1("locked", seed, 3)            # the exam covers Step-1 phrases too
    elif kind == "human":
        seed = secrets.randbits(32)
        items, name = build_human(seed), f"human_{seed:08x}"
        recording_sheet(items, f"testsets/{name}_SHEET.md")
    else:
        raise SystemExit("use: dev | dev2 | step1 | locked | human")
    path = f"testsets/{name}.json"
    json.dump({"name": name, "kind": kind, "seed": seed, "items": items},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    traps = {}
    for it in items:
        for t in it["traps"]:
            traps[t] = traps.get(t, 0) + 1
    print(f"Wrote {path}: {len(items)} lines. Traps: {traps}")
    if kind == "human":
        print(f"Recording sheet: testsets/{name}_SHEET.md")
    if kind == "locked":
        print("Do NOT open this file. Run it once with scripts/run_eval.py after freezing the code.")


if __name__ == "__main__":
    main()
