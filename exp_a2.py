"""
Experiment A2 — test the two Step-0 fixes BEFORE writing them (rules decided in advance).

From A1 (your voice), two runway flags looked fixable in text:
  Fix W : "right at Bravo" heard as "writer Bravo"  ->  read "writer" after a runway number as "right"
  Fix G : transcribe glued "two niner" into "290" while verbatim heard "two niner"
          -> when the runway is impossible, ask the SAME audio again in verbatim and use it

Both could also CREATE silent errors, so we test on 6 dev voices first (never the locked voices).

RULES FIXED NOW (before seeing results):
  Fix W is added only if: "writer" shows up for "right at" in 2+ different voices
                          AND never shows up for "left at" or "right" without "at".
  Fix G is added only if: it rescues 2+ voices AND the verbatim runway is NEVER a real but wrong runway.
  Even if added, both show AMBER (never green).

Run:   python exp_a2.py
Cost:  24 TTS + 4 phrases x 6 voices x 2 audio versions x 2 styles = 96 STT  ~ Rs 5
"""
import os
import json
import hashlib
import datetime
import soundfile as sf

from gnani_client import tts, stt
from radio_sim import radio
from scoring import judge

AIRPORT = "VIDP"
TRAFFIC = {"AIC2817", "AIC2871", "AKJ1123", "FOLLOWME3", "IGO5134"}
VOICES = ["Avinash", "Riyaa", "Harshad", "Prakash", "Devansh", "Shubham"]   # dev voices (timbre-v3.0)
PHRASES = {   # id: (text, true runway, what it tests)
    "R_at":  ("IFLY five one three four, cross runway two niner right at Bravo, report vacated.", "29R", "the A1 problem"),
    "L_at":  ("IFLY five one three four, cross runway two niner left at Bravo, report vacated.", "29L", "control: must never give 'writer'"),
    "R_end": ("IFLY five one three four, cross runway two niner right, report vacated.", "29R", "control: 'right' without 'at'"),
    "R_11":  ("IFLY five one three four, cross runway one one right at Charlie, report vacated.", "11R", "same words, other number"),
}


def main():
    os.makedirs("audio_eval/exp_a2", exist_ok=True)
    rows = []
    for pid, (text, rwy, why) in PHRASES.items():
        print(f"\n[{pid}] {why}\n  said: {text}")
        for v in VOICES:
            clean = f"audio_eval/exp_a2/{pid}_{v}.wav"
            if not tts(text, v, "timbre-v3.0", "en-IN", clean):
                continue
            x, sr = sf.read(clean)
            noisy = f"audio_eval/exp_a2/{pid}_{v}_snr10.wav"
            seed = int(hashlib.md5(noisy.encode()).hexdigest()[:8], 16)
            sf.write(noisy, radio(x, sr, 10, seed=seed), 8000, subtype="PCM_16")
            for vname, p in (("clean", clean), ("radio", noisy)):
                got = {}
                for st in ("transcribe", "verbatim"):
                    t = stt(p, "tower", fmt=st)
                    o, r = judge(t, AIRPORT, TRAFFIC, rwy, "IGO5134")
                    got[st] = {"text": t, "outcome": o, "runway": r["runway"]}
                    print(f"  {v:8} {vname:5} {st:10} {o:5} {t}")
                rows.append({"phrase": pid, "voice": v, "audio": vname, "truth": rwy, **got})
    out = f"results/exp_a2_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    os.makedirs("results", exist_ok=True)
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nSaved {out}. Paste the whole output; I will apply the rules at the top, nothing else.")


if __name__ == "__main__":
    main()
