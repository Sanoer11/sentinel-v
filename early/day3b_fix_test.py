"""
Sentinel-V — Day 3b (revised): make Prisma hear better WITHOUT hiding real mistakes.

DROPPED: the traffic-list hint (keyterms with real callsigns like "IFLY 5134").
  Why: it pushes Prisma toward flights it expects. Similar callsigns (2817/2871) are the #1
  cause of real ATC mix-ups, and the hint can make a wrong callsign "sound" right.

KEPT, but only in a safe way: previous_text (what the tower just said) for readbacks.
  Two listens per readback:
    Listen 1 (neutral, no hint)  -> this ALWAYS decides if it heard a clear number.
    Listen 2 (with tower's words)-> used ONLY when listen 1 heard nothing usable.
                                    Its answer is never green: it is AMBER ("probably, please confirm").
  So the hint can fill a gap, but can never overwrite a number that was clearly heard.

TESTED: the denoiser (spectral gating) before Prisma. No hints, so it can't hide mistakes;
  the only question is whether it helps or hurts accuracy.

Lines 17-19 are deliberate WRONG readbacks. We check whether the mistake survives.

Run:   python early/day3b_fix_test.py   (reuses audio_day3/ from Day 3, makes 3 new TTS lines)
Cost:  ~184 STT calls + 3 TTS  ≈ Rs 9-11
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
from scipy.signal import stft, istft

from day1_prisma_test import BASE, ATC_TOPIC, post_with_retry, tts
from day2_radio_test import radio, RADIO_SR
from day3_fair_test import LINES, TRAFFIC, KEYTERMS
from sentinel_parse import extract

SNR_LEVELS = [20, 10, 5, 0]

WRONG_READBACKS = [
    # id, airport, channel, voice, model, lang, text, spoken_runway, spoken_callsign, tower_line, what's wrong
    (17, "VIDP", "pilot", "Shivani", "timbre-v3.0", "en-IN",
     "Line up and wait runway two niner right, Air India two eight seven one.",
     "29R", "AIC2871", 3, "tower said 29L, pilot says 29R"),
    (18, "VIDP", "pilot", "Yashraj", "timbre-v3.0", "en-IN",
     "Cleared to land runway two eight, IFLY five one three four.",
     "28", "IGO5134", 9, "tower said 27, pilot says 28 (valid runway)"),
    (19, "VIDP", "pilot", "Chetana", "timbre-v3.0", "en-IN",
     "Cleared to land runway two seven, IFLY five one two four.",
     "27", "IGO5124", 9, "tower called 5134, pilot answers as 5124"),
]
READBACK_OF = {2: 1, 4: 3, 6: 5, 8: 7, 11: 10, 17: 3, 18: 9, 19: 9}


def denoise(x, sr):
    """Spectral gating: find the noise level per frequency in the quiet parts, turn it down."""
    _, _, Z = stft(x, sr, nperseg=256, noverlap=192)
    mag = np.abs(Z)
    floor = np.percentile(mag, 20, axis=1, keepdims=True)
    gain = np.clip(1 - 1.5 * floor / (mag + 1e-9), 0.15, 1.0)
    _, y = istft(Z * gain, sr, nperseg=256, noverlap=192)
    y = y[:len(x)]
    return 0.8 * y / (np.max(np.abs(y)) + 1e-9)


def stt(path, channel, prev=None):
    """Same settings as Day 3 (general ATC words only — no flight numbers). prev = tower's words."""
    data = {"model": "prisma-v3.0", "format": "transcribe",
            "language_code": "hi-IN,en-IN,mr-IN" if channel == "airside" else "en-IN",
            "keyterms": json.dumps(KEYTERMS, ensure_ascii=False), "topic": ATC_TOPIC}
    if prev:
        data["previous_text"] = prev
    with open(path, "rb") as f:
        r = post_with_retry(f"{BASE}/stt/v3", data=data,
                            files={"audio_file": (os.path.basename(path), f, "audio/wav")})
    try:
        b = r.json()
    except ValueError:
        return f"<error {r.status_code}>"
    return b.get("transcript", "") if b.get("success") else f"<error {b}>"


def two_listens(neutral_text, hinted_text, ap):
    """Listen 1 decides if it is usable. Listen 2 only fills a gap, and only as AMBER."""
    r1 = extract(neutral_text, ap, TRAFFIC[ap])
    if r1["status"] == "CONFIRMED":
        return r1, "GREEN"
    r2 = extract(hinted_text, ap, TRAFFIC[ap]) if hinted_text else None
    if r2 and r2["status"] == "CONFIRMED":
        return r2, "AMBER"
    return r1, "FLAG"


def grade(r, colour, rwy, cs):
    if colour == "FLAG" or r["status"] == "FLAGGED":
        return "FLAG"
    right = (r["runway"], r["callsign"]) == (rwy, cs)
    if not right:
        return "WRONG"
    if colour == "AMBER":
        return "AMBER"
    return "OK*" if r["corrected"] else "OK"


def new_tally():
    return {"OK": 0, "OK*": 0, "AMBER": 0, "FLAG": 0, "WRONG": 0}


def main():
    texts = {l[0]: l[7] for l in LINES}
    jobs = [(l[0], l[1], l[2], l[8], l[9]) for l in LINES]
    for lid, ap, ch, voice, model, lang, text, rwy, cs, tw, why in WRONG_READBACKS:
        tts(text, voice, model, lang, f"audio_day3/line{lid:02d}_{ch}.wav")
        texts[lid] = text
        jobs.append((lid, ap, ch, rwy, cs))

    t_noise = {"raw": {}, "denoised": {}}          # lines 1-16
    t_rb = {"listen1 only": {}, "two listens": {}}   # readback lines 2,4,6,8,11
    masking = {"listen1 only": [0, 0], "hint only (unsafe)": [0, 0], "two listens": [0, 0]}
    rows = []

    for lid, ap, ch, rwy, cs in jobs:
        clean = f"audio_day3/line{lid:02d}_{ch}.wav"
        if not os.path.exists(clean):
            print(f"missing {clean} — run early/day3_fair_test.py first"); continue
        x, sr = sf.read(clean)
        tower = READBACK_OF.get(lid)
        print(f"[{lid}] {texts[lid]}" + (f"   (reads back line {tower})" if tower else ""))
        for snr in SNR_LEVELS:
            p = f"audio_day3/line{lid:02d}_{ch}_snr{snr}.wav"
            if not os.path.exists(p):
                sf.write(p, radio(x, sr, snr, seed=7000 + lid * 10 + snr), RADIO_SR, subtype="PCM_16")
            pd = p.replace(".wav", "_dn.wav")
            if not os.path.exists(pd):
                y, s2 = sf.read(p)
                sf.write(pd, denoise(y, s2), s2, subtype="PCM_16")

            raw_t = stt(p, ch)
            dn_t = stt(pd, ch)
            hint_t = stt(p, ch, prev=texts[tower]) if tower else None
            row = {"id": lid, "snr": snr, "truth": [rwy, cs], "raw": raw_t, "denoised": dn_t, "hinted": hint_t}
            rows.append(row)
            print(f"  {snr:>2}dB raw     : {raw_t}\n       denoised: {dn_t}" +
                  (f"\n       hinted  : {hint_t}" if hint_t else ""))

            if lid <= 16:
                for name, t in (("raw", raw_t), ("denoised", dn_t)):
                    r = extract(t, ap, TRAFFIC[ap])
                    t_noise[name].setdefault(snr, new_tally())[grade(r, "GREEN", rwy, cs)] += 1
                if tower:
                    r1, c1 = two_listens(raw_t, None, ap)
                    t_rb["listen1 only"].setdefault(snr, new_tally())[grade(r1, c1, rwy, cs)] += 1
                    r2, c2 = two_listens(raw_t, hint_t, ap)
                    t_rb["two listens"].setdefault(snr, new_tally())[grade(r2, c2, rwy, cs)] += 1
            else:
                # wrong readback: is the pilot's ACTUAL (wrong) value still visible?
                def kept(t_or_result):
                    r = t_or_result if isinstance(t_or_result, dict) else extract(t_or_result, ap, TRAFFIC[ap])
                    if lid == 19:
                        return "5124" in re.sub(r"\D", "", (r["normalized"]))
                    return r["runway"] == rwy
                r_tl, c_tl = two_listens(raw_t, hint_t, ap)
                for name, ok in (("listen1 only", kept(raw_t)),
                                 ("hint only (unsafe)", kept(hint_t)),
                                 ("two listens", kept(r_tl) if c_tl != "FLAG" else True)):
                    masking[name][0 if ok else 1] += 1

    def show(title, table, labels):
        print(f"\n{title}")
        print(f"{'':<14}" + "".join(f"| {s:>2}dB  OK/OK*/AMB/FLG/WRG " for s in SNR_LEVELS))
        for name in labels:
            cells = []
            for snr in SNR_LEVELS:
                t = table[name].get(snr, new_tally())
                cells.append(f"|   {t['OK']:>2}/{t['OK*']:>2}/{t['AMBER']:>2}/{t['FLAG']:>2}/{t['WRONG']:>2}         ")
            print(f"{name:<14}" + "".join(cells))

    show("TABLE 1 — does the denoiser help? (lines 1-16)", t_noise, ["raw", "denoised"])
    show("TABLE 2 — does the second listen rescue readbacks? (lines 2,4,6,8,11)", t_rb,
         ["listen1 only", "two listens"])
    print("\nTABLE 3 — wrong readbacks (lines 17-19, 12 clips): is the pilot's mistake still visible?")
    for name, (k, l) in masking.items():
        print(f"  {name:<20} kept {k:>2}   HIDDEN {l:>2}")
    print("  ('two listens' counts a FLAG as kept: a human gets asked, so nothing is hidden.)")

    with open("early/results_day3b.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("\nSaved results_day3b.json")


if __name__ == "__main__":
    main()