"""
Sentinel-V — Day 2 experiment
Question: does Prisma still catch callsigns + runways when the audio sounds like a real radio?

Day 1 used clean studio audio. Real ATC is a walkie-talkie: narrow band, static, crackle,
8 kHz codec. So we take Day 1's clips and degrade them like a radio channel at 4 noise levels:
  SNR 20 dB (good radio) -> 10 dB (busy) -> 5 dB (bad) -> 0 dB (terrible)

We also add the NORMALIZER — our own code that sits after Prisma and fixes what Day 1 showed:
  - context mode sometimes returns spoken words ("two niner right") instead of digits
  - "I fly" vs "IFLY", "29R right" duplicates, glued tokens like "27P4"
  - Marathi/Hindi speakers saying English digits in Devanagari ("टू सेव्हन")
Every later layer (runway tracker, conflict checks) reads the NORMALIZED text.

Setup:
  pip install numpy scipy soundfile
  python early/day2_radio_test.py        (uses Day 1's audio/ folder and .env)

Cost: 11 lines x 4 noise levels x 2 modes = 88 STT calls (~Rs 4 at Day 1 rates).
Output: audio_radio/*.wav (listen to them!) + results_day2.json + score table.
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative

import re
import json
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, resample_poly

from day1_prisma_test import LINES, stt  # reuse Day 1 clips + Prisma call

SNR_LEVELS = [20, 10, 5, 0]
RADIO_SR = 8000
os.makedirs("audio_radio", exist_ok=True)

# ---------------------------------------------------------------------------
# 1. RADIO CHANNEL SIMULATOR
# ---------------------------------------------------------------------------
BAND = butter(4, [300, 3400], btype="band", fs=RADIO_SR, output="sos")  # voice-radio band


def mulaw_codec(x, mu=255):
    """Compress -> 8-bit quantise -> expand. Same idea as telephone/radio codecs."""
    c = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    c = np.round(c * 127) / 127
    return np.sign(c) * ((1 + mu) ** np.abs(c) - 1) / mu


def radio(x, sr, snr_db, seed):
    rng = np.random.default_rng(seed)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = resample_poly(x, RADIO_SR, sr)              # down to 8 kHz
    x = sosfilt(BAND, x)                            # cut lows and highs
    x = 0.7 * x / (np.max(np.abs(x)) + 1e-9)

    noise = sosfilt(BAND, rng.normal(size=len(x)))  # radio hiss in the same band
    p_sig = np.mean(x ** 2)
    noise *= np.sqrt(p_sig / (10 ** (snr_db / 10)) / (np.mean(noise ** 2) + 1e-12))

    crackle = np.zeros(len(x))                      # static pops, ~20 per second
    idx = rng.choice(len(x), size=int(20 * len(x) / RADIO_SR), replace=False)
    crackle[idx] = rng.uniform(-0.3, 0.3, size=len(idx))

    y = np.clip(x + noise + crackle, -0.9, 0.9)     # mild clipping like an overdriven mic
    return mulaw_codec(y)


# ---------------------------------------------------------------------------
# 2. NORMALIZER (our code, runs on every Prisma transcript)
# ---------------------------------------------------------------------------
DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "tree": "3", "four": "4",
    "fower": "4", "five": "5", "fife": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "niner": "9",
    # English digits spoken by Hindi/Marathi speakers, written in Devanagari
    "ज़ीरो": "0", "झिरो": "0", "जीरो": "0", "वन": "1", "टू": "2", "थ्री": "3", "फोर": "4",
    "फाइव": "5", "फाईव्ह": "5", "सिक्स": "6", "सेवन": "7", "सेव्हन": "7", "एट": "8",
    "नाइन": "9", "नाईन": "9",
}
SIDE = {"right": "R", "left": "L", "centre": "C", "center": "C",
        "r": "R", "l": "L", "c": "C", "राइट": "R", "लेफ्ट": "L"}
FIXES = [  # (regex, replacement) — callsigns and terms Prisma splits or spells differently
    (r"\bi\s*fly\b", "IFLY"),
    (r"\bair\s*india\b", "Air India"),
    (r"\bfollow\s*me\b|फॉलो\s*मी", "Follow Me"),
    (r"\bbird\s*chaser\b|बर्ड\s*चेसर", "Bird Chaser"),
    (r"रनवे", "runway"),
    (r"टॅक्सीवे|टैक्सीवे", "taxiway"),
    (r"\bएफ\s*ओ\s*डी\b|\bf\s*o\s*d\b", "FOD"),
]


def normalize(text):
    t = text
    for pat, rep in FIXES:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = re.sub(r"(\d)([A-Za-z\u0900-\u097F])", r"\1 \2", t)   # "27P4" -> "27 P4"
    t = re.sub(r"([A-Za-z])(\d)", r"\1 \2", t)                # "P4" -> "P 4"
    t = re.sub(r"([,.।!?])", r" \1 ", t)
    tokens = t.split()

    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low in DIGIT_WORDS or tok.isdigit():
            num = ""
            while i < len(tokens) and (tokens[i].lower() in DIGIT_WORDS or tokens[i].isdigit()):
                num += DIGIT_WORDS.get(tokens[i].lower(), tokens[i])
                i += 1
            # runway side: "29 right" / "29 R" / "29R right" -> "29R"
            while i < len(tokens) and tokens[i].lower() in SIDE:
                if not num[-1].isalpha():
                    num += SIDE[tokens[i].lower()]
                i += 1
            out.append(num)
            continue
        out.append(tok)
        i += 1

    s = " ".join(out)
    return re.sub(r"\s+([,.।!?])", r"\1", s).strip()


def caught(text, token):
    """STRICT: the token must appear as a whole word. '27' does NOT match '270'."""
    words = re.findall(r"[A-Za-z0-9]+", text.upper())
    return token.upper() in words


# ---------------------------------------------------------------------------
# 3. RUN
# ---------------------------------------------------------------------------
def main():
    rows, table = [], {}
    for lid, ch, voice, model, lang, text, must in LINES:
        src = f"audio/line{lid:02d}_{ch}.wav"
        if not os.path.exists(src):
            print(f"missing {src} — run day1 first")
            continue
        x, sr = sf.read(src)
        print(f"\n[{lid}] {ch.upper()}: {text}")
        for snr in SNR_LEVELS:
            dst = f"audio_radio/line{lid:02d}_{ch}_snr{snr}.wav"
            if not os.path.exists(dst):
                sf.write(dst, radio(x, sr, snr, seed=lid * 100 + snr), RADIO_SR, subtype="PCM_16")
            for mode in ("plain", "context"):
                raw = stt(dst, ch, with_context=(mode == "context"))
                norm = normalize(raw)
                raw_ok = sum(caught(raw, t) for t in must)
                norm_ok = sum(caught(norm, t) for t in must)
                key = (snr, mode)
                agg = table.setdefault(key, {"raw": 0, "norm": 0, "total": 0})
                agg["raw"] += raw_ok
                agg["norm"] += norm_ok
                agg["total"] += len(must)
                print(f"  SNR {snr:>2} {mode:<7} raw[{raw_ok}/{len(must)}] norm[{norm_ok}/{len(must)}]  {norm}")
                rows.append({"id": lid, "channel": ch, "snr": snr, "mode": mode,
                             "must_catch": must, "raw": raw, "normalized": norm,
                             "raw_caught": raw_ok, "norm_caught": norm_ok})

    print("\n========== CRITICAL-TOKEN ACCURACY (callsign + runway) ==========")
    print(f"{'SNR':>5} | {'plain raw':>10} | {'plain norm':>10} | {'ctx raw':>8} | {'ctx norm':>8}")
    for snr in SNR_LEVELS:
        cells = []
        for mode in ("plain", "context"):
            a = table.get((snr, mode), {"raw": 0, "norm": 0, "total": 1})
            cells += [100 * a["raw"] / a["total"], 100 * a["norm"] / a["total"]]
        print(f"{snr:>3}dB | {cells[0]:>9.0f}% | {cells[1]:>9.0f}% | {cells[2]:>7.0f}% | {cells[3]:>7.0f}%")

    with open("early/results_day2.json", "w", encoding="utf-8") as f:
        json.dump({"table": {f"{k[0]}dB_{k[1]}": v for k, v in table.items()}, "rows": rows},
                  f, ensure_ascii=False, indent=2)
    print("\nSaved results_day2.json. Listen to audio_radio/*_snr5.wav — that's what Prisma is hearing.")


if __name__ == "__main__":
    main()