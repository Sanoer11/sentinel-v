"""
Sentinel-V — Day 3: the FAIR test. Resolves the 3 open problems from Day 2.

PROBLEM 1  "Fixes were tuned on the same data"
  -> sentinel_parse.py is FROZEN. Its fingerprint is printed at the start and saved.
     Rule: no edits to the parser until this run's results are recorded.
PROBLEM 2  "Only 11 lines, all Gnani TTS voices"
  -> 16 brand-new lines, new callsigns, new voices never used before
     (Kalpana, Yashraj, Shivani, Tarika, Chetana, Lakshmi, Vasudha, Zahira),
     plus YOUR OWN VOICE: put recordings in my_voice/ (see bottom).
PROBLEM 3  "The dangerous case never happened"
  -> lines are built to hit VALID-runway traps on purpose:
       Delhi has 27, 28, 29L, 29R  ("two seven / two eight / two niner" all exist)
       Delhi 11L vs 11R, Pune 10 vs 28
       Delhi traffic has AIC2817 and AIC2871 on frequency at the same time
     and a SECOND OPINION: every clip also goes to Prisma v2.5. If v2.5 and v3.0
     disagree on runway or callsign -> FLAG. We score with and without this vote.

Run:   python early/day3_fair_test.py
Cost:  16 lines x 4 noise levels x 2 models = 128 STT calls + 16 TTS (~Rs 7)
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative

import re
import json
import hashlib
import soundfile as sf

from day1_prisma_test import BASE, ATC_KEYTERMS, ATC_TOPIC, post_with_retry, tts
from day2_radio_test import radio, RADIO_SR
import sentinel_parse
from sentinel_parse import extract

SNR_LEVELS = [20, 10, 5, 0]
os.makedirs("audio_day3", exist_ok=True)
os.makedirs("my_voice", exist_ok=True)

TRAFFIC = {
    "VIDP": {"AIC2817", "AIC2871", "IGO5134", "AKJ1123", "FOLLOWME3"},
    "VAPO": {"IGO2241", "AIC947"},
    "VABB": {"AKJ1402", "IGO6318", "BIRDCHASER1"},
}

# id, airport, channel, voice, tts_model, tts_lang, v25_lang, text, true_runway, true_callsign, trap
LINES = [
    (1, "VIDP", "tower", "Kalpana", "timbre-v3.0", "en-IN", "en-IN",
     "Air India two eight one seven, runway two eight, cleared to land.", "28", "AIC2817",
     "28 vs 27/29 all valid; 2817 vs 2871 both on frequency"),
    (2, "VIDP", "pilot", "Yashraj", "timbre-v3.0", "en-IN", "en-IN",
     "Cleared to land runway two eight, Air India two eight one seven.", "28", "AIC2817", "readback of 1"),
    (3, "VIDP", "tower", "Kalpana", "timbre-v3.0", "en-IN", "en-IN",
     "Air India two eight seven one, line up and wait runway two niner left.", "29L", "AIC2871",
     "2871 vs 2817; 29L vs 29R"),
    (4, "VIDP", "pilot", "Shivani", "timbre-v3.0", "en-IN", "en-IN",
     "Line up and wait runway two niner left, Air India two eight seven one.", "29L", "AIC2871", "readback of 3"),
    (5, "VIDP", "tower", "Tarika", "timbre-v3.0", "en-IN", "en-IN",
     "IFLY five one three four, cross runway two niner right at Bravo, report vacated.", "29R", "IGO5134",
     "29R vs 29L"),
    (6, "VIDP", "pilot", "Chetana", "timbre-v3.0", "en-IN", "en-IN",
     "Crossing runway two niner right, IFLY five one three four.", "29R", "IGO5134", "readback of 5"),
    (7, "VIDP", "tower", "Tarika", "timbre-v3.0", "en-IN", "en-IN",
     "Akasa Air one one two three, runway one one left, cleared for takeoff.", "11L", "AKJ1123",
     "11L vs 11R"),
    (8, "VIDP", "pilot", "Lakshmi", "timbre-v3.0", "en-IN", "en-IN",
     "Runway one one left, cleared for takeoff, Akasa Air one one two three.", "11L", "AKJ1123", "readback of 7"),
    (9, "VIDP", "tower", "Kalpana", "timbre-v3.0", "en-IN", "en-IN",
     "IFLY five one three four, runway two seven, cleared to land.", "27", "IGO5134",
     "27 vs 28 vs 29: the exact 'two to three' weakness from Day 2, but every neighbour is valid"),
    (10, "VAPO", "tower", "Vasudha", "timbre-v3.0", "en-IN", "en-IN",
     "IFLY two two four one, runway one zero, cleared for takeoff.", "10", "IGO2241", "10 vs 28"),
    (11, "VAPO", "pilot", "Yashraj", "timbre-v3.0", "en-IN", "en-IN",
     "Runway one zero, cleared for takeoff, IFLY two two four one.", "10", "IGO2241", "readback of 10"),
    (12, "VAPO", "tower", "Vasudha", "timbre-v3.0", "en-IN", "en-IN",
     "Air India niner four seven, runway two eight, cleared to land.", "28", "AIC947", "28 vs 10"),
    (13, "VABB", "tower", "Lakshmi", "timbre-v3.0", "en-IN", "en-IN",
     "Akasa Air one four zero two, runway one four, cleared to land.", "14", "AKJ1402", "14 vs 32"),
    (14, "VABB", "tower", "Shivani", "timbre-v3.0", "en-IN", "en-IN",
     "IFLY six three one eight, hold short runway three two.", "32", "IGO6318", "32 vs 27/14"),
    (15, "VIDP", "airside", "Yashraj", "timbre-v3.0", "hi-IN", "hi-IN",
     "टावर, फॉलो मी थ्री, रनवे टू नाइन राइट क्रॉस करना है, होल्डिंग पॉइंट ब्रावो पर हूँ।", "29R", "FOLLOWME3",
     "Hindi airside, 29R vs 29L"),
    (16, "VABB", "airside", "Zahira", "timbre-v2.5", "mr-IN", "mr-IN",
     "टॉवर, बर्ड चेसर वन, रनवे थ्री टू वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय.", "32", "BIRDCHASER1",
     "Marathi airside, 32"),
]

KEYTERMS = sorted(set(ATC_KEYTERMS + ["Akasa Air", "hold short", "Charlie", "holding point"]))


def stt_v30(path, channel):
    data = {"model": "prisma-v3.0", "format": "transcribe",
            "language_code": "hi-IN,en-IN,mr-IN" if channel == "airside" else "en-IN",
            "keyterms": json.dumps(KEYTERMS, ensure_ascii=False), "topic": ATC_TOPIC}
    return _post(path, data)


def stt_v25(path, lang):
    # Prisma v2.5: one language, no keyterms. Independent second opinion.
    return _post(path, {"language_code": lang, "format": "transcribe"})


def _post(path, data):
    with open(path, "rb") as f:
        r = post_with_retry(f"{BASE}/stt/v3", data=data,
                            files={"audio_file": (os.path.basename(path), f, "application/octet-stream")})
    try:
        body = r.json()
    except ValueError:
        return f"<error {r.status_code}>"
    return body.get("transcript", "") if body.get("success") else f"<error {body}>"


def judge(res, rwy, cs):
    if res["status"] == "FLAGGED":
        return "FLAG"
    return "OK" if (res["runway"], res["callsign"]) == (rwy, cs) else "WRONG"


def score(lid, ap, rwy, cs, t30, t25, rows, label):
    r30 = extract(t30, ap, TRAFFIC[ap])
    r25 = extract(t25, ap, TRAFFIC[ap])
    single = judge(r30, rwy, cs)
    if single == "FLAG":
        voted = "FLAG"
    elif r25["status"] == "CONFIRMED" and (r25["runway"], r25["callsign"]) != (r30["runway"], r30["callsign"]):
        voted = "FLAG"                    # the two models disagree -> ask a human
    else:
        voted = single                    # v2.5 agrees or v2.5 heard nothing usable
    rows.append({"id": lid, "cond": label, "airport": ap, "truth": [rwy, cs],
                 "v30": t30, "v25": t25, "v30_parsed": [r30["runway"], r30["callsign"], r30["problems"]],
                 "v25_parsed": [r25["runway"], r25["callsign"], r25["problems"]],
                 "corrected_callsign": r30["corrected"], "single": single, "voted": voted})
    mark = {"OK": "ok  ", "FLAG": "FLAG", "WRONG": "WRONG"}
    print(f"  {label:<9} single={mark[single]:<5} vote={mark[voted]:<5} v3.0: {t30}")
    if single == "WRONG" or voted == "WRONG":
        print(f"            !!! DANGEROUS: parsed {r30['runway']}/{r30['callsign']}  truth {rwy}/{cs}")
    return single, voted


def main():
    fp = hashlib.sha256(open(sentinel_parse.__file__, "rb").read()).hexdigest()[:12]
    print(f"Parser FROZEN, fingerprint {fp}. Do not edit sentinel_parse.py before saving these results.\n")

    rows, tally = [], {}
    for lid, ap, ch, voice, model, lang, v25lang, text, rwy, cs, trap in LINES:
        print(f"[{lid}] {ap} {ch} ({voice})  trap: {trap}\n      {text}")
        clean = f"audio_day3/line{lid:02d}_{ch}.wav"
        if not tts(text, voice, model, lang, clean):
            continue
        x, sr = sf.read(clean)
        for snr in SNR_LEVELS:
            p = f"audio_day3/line{lid:02d}_{ch}_snr{snr}.wav"
            if not os.path.exists(p):
                sf.write(p, radio(x, sr, snr, seed=7000 + lid * 10 + snr), RADIO_SR, subtype="PCM_16")
            s, v = score(lid, ap, rwy, cs, stt_v30(p, ch), stt_v25(p, v25lang), rows, f"{snr}dB")
            for key, outcome in ((("tts", snr, "single"), s), (("tts", snr, "vote"), v)):
                tally.setdefault(key, {"OK": 0, "FLAG": 0, "WRONG": 0})[outcome] += 1

        # YOUR VOICE: my_voice/line01.m4a (or .wav/.mp3) -> sent as-is, real human audio
        for ext in ("wav", "m4a", "mp3"):
            hv = f"my_voice/line{lid:02d}.{ext}"
            if os.path.exists(hv):
                s, v = score(lid, ap, rwy, cs, stt_v30(hv, ch), stt_v25(hv, v25lang), rows, "my voice")
                for key, outcome in ((("human", 0, "single"), s), (("human", 0, "vote"), v)):
                    tally.setdefault(key, {"OK": 0, "FLAG": 0, "WRONG": 0})[outcome] += 1
                break
        print()

    print("================ DAY 3 FAIR TEST (OK / FLAG / WRONG) ================")
    print(f"{'condition':<12} | {'v3.0 alone':^18} | {'v3.0 + v2.5 vote':^18}")
    keys = [("tts", s) for s in SNR_LEVELS] + [("human", 0)]
    for src, snr in keys:
        a, b = tally.get((src, snr, "single")), tally.get((src, snr, "vote"))
        if not a:
            continue
        name = f"TTS {snr}dB" if src == "tts" else "your voice"
        fmt = lambda t: f"{t['OK']:>2} / {t['FLAG']:>2} / {t['WRONG']:>2}"
        print(f"{name:<12} | {fmt(a):^18} | {fmt(b):^18}")
    print("\nWRONG = confirmed but wrong. That column is the one that decides if the idea is safe.")

    with open("early/results_day3.json", "w", encoding="utf-8") as f:
        json.dump({"parser_fingerprint": fp, "rows": rows,
                   "tally": {f"{k[0]}_{k[1]}_{k[2]}": v for k, v in tally.items()}},
                  f, ensure_ascii=False, indent=2)
    print("Saved results_day3.json")


if __name__ == "__main__":
    main()