"""
Experiment A1 — find the CAUSE before fixing (no guessing). Uses your 6 real recordings.

Question 1: Is "IFLY" lost under radio because the START of the call is cut, or because of noise?
            Same noise, cut ON vs cut OFF. Only the first 60-200 ms differ.
Question 2: Do "niner right" (290 / 299) and "two eight, cleared" (2808) fail because Prisma
            MISHEARS them, or because its number-writing step (format=transcribe) glues words
            into digits? We ask for the same audio in 3 output styles:
              transcribe = digits (what we use now)
              verbatim   = spoken words, no number conversion
              codemix    = English words kept, numbers mostly as words

Run:   python experiments/exp_a1.py
Cost:  6 recordings x 3 audio versions x 3 styles = 54 calls  ≈ Rs 3
Output: a table per recording + results/exp_a1_<time>.json
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import re
import json
import glob
import shutil
import hashlib
import datetime
import subprocess
import soundfile as sf

from gnani_client import stt
from radio_sim import radio

STYLES = ["transcribe", "verbatim", "codemix"]
WATCH = {   # the exact words we care about per recording
    "h001a": "two eight, cleared (expect 28)",
    "h003a": "two niner left (expect 29 left)",
    "h005a": "IFLY ... two niner right at Bravo (expect IFLY, 29 right)",
    "h009a": "IFLY five one three four (expect IFLY)",
    "h010a": "IFLY two two four one (expect IFLY)",
    "h015a": "Follow Me three, two nine right (expect 29 right)",
}


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("needs ffmpeg: brew install ffmpeg")
    files = sorted(glob.glob("my_voice/sanoer_h0*a.m4a"))
    if not files:
        raise SystemExit("no recordings in my_voice/")
    os.makedirs("audio_eval/exp_a1", exist_ok=True)
    out = []
    for f in files:
        iid = re.search(r"_(h\d{3}a)\.", f).group(1)
        channel = "airside" if iid == "h015a" else "tower"
        wav = f"audio_eval/exp_a1/{iid}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f, "-ac", "1", "-ar", "16000", wav], check=True)
        x, sr = sf.read(wav)
        seed = int(hashlib.md5(f"audio_eval/sanoer_{iid}_snr10.wav".encode()).hexdigest()[:8], 16)  # same noise as run_eval
        versions = {"as recorded": f}          # the original file, exactly what run_eval sent
        for clip in (True, False):
            p = f"audio_eval/exp_a1/{iid}_snr10_{'cut' if clip else 'nocut'}.wav"
            sf.write(p, radio(x, sr, 10, seed=seed, clip=clip), 8000, subtype="PCM_16")
            versions["radio, start cut" if clip else "radio, no cut"] = p
        print(f"\n[{iid}] said: {WATCH.get(iid, '')}")
        for vname, p in versions.items():
            for st in STYLES:
                t = stt(p, channel, fmt=st)
                out.append({"id": iid, "audio": vname, "style": st, "heard": t})
                print(f"  {vname:<17} {st:<10} {t}")
    os.makedirs("results", exist_ok=True)
    path = f"results/exp_a1_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nSaved {path}. Paste the whole output — I will read every line, nothing is auto-scored here.")


if __name__ == "__main__":
    main()
