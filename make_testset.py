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
  python make_testset.py dev
  python make_testset.py locked
  python make_testset.py human
"""
import os
import sys
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


def build(kind, seed, n_pairs, n_airside):
    rng = random.Random(seed)
    items = []
    for i in range(n_pairs):
        items += flight_lines(rng, "dev" if kind == "dev" else "locked", i)
    for i in range(n_airside):
        items.append(airside_line(rng, "dev" if kind == "dev" else "locked", i))
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
            f.write(f"| {it['id']} | {it.get('roman', it['text'])} |\n")


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "dev"
    os.makedirs("testsets", exist_ok=True)
    if kind == "dev":
        seed, items, name = 1, build("dev", 1, 24, 12), "dev"
    elif kind == "locked":
        seed = secrets.randbits(32)
        items, name = build("locked", seed, 60, 30), f"locked_{seed:08x}"
    elif kind == "human":
        seed = secrets.randbits(32)
        items = build("locked", seed, 12, 6)
        for it in items:
            it["id"] = "h" + it["id"][1:]
        name = f"human_{seed:08x}"
        recording_sheet(items, f"testsets/{name}_SHEET.md")
    else:
        raise SystemExit("use: dev | locked | human")
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
        print("Do NOT open this file. Run it once with run_eval.py after freezing the code.")


if __name__ == "__main__":
    main()
