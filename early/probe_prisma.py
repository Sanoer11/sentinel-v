"""
Does Prisma send back anything besides the text? (word confidence, word timings, alternatives)

Why: the 15 false REDs are digits misheard in noise. The text looks exactly like a real pilot mistake,
and A6 showed a second listen hears the same digit. The ONLY software way left to tell them apart is
if Prisma says how SURE it was about each word. Web search and the launch articles say nothing about it,
so we look at the raw reply ourselves.

Run:   python early/probe_prisma.py                      (default clip: a pilot readback from DEL_2023, 10 dB)
       python early/probe_prisma.py path/to/clip.wav
Cost:  3 STT calls (transcribe, verbatim, codemix) ~ Rs 0.15
Paste the whole output.
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
from gnani_client import stt_raw

CLIP = sys.argv[1] if len(sys.argv) > 1 else "audio_eval/scen/DEL_2023_1_p1_snr10.wav"


def paths(x, pre=""):
    """Every field name in the reply, e.g. words[].confidence"""
    out = []
    if isinstance(x, dict):
        for k, v in x.items():
            out.append(f"{pre}{k}  ({type(v).__name__})")
            out += paths(v, f"{pre}{k}.")
    elif isinstance(x, list) and x:
        out += paths(x[0], pre[:-1] + "[].")
    return out


def short(x):
    if isinstance(x, dict):
        return {k: short(v) for k, v in x.items()}
    if isinstance(x, list):
        return [short(v) for v in x[:4]] + ([f"... {len(x) - 4} more"] if len(x) > 4 else [])
    return x


for fmt in ("transcribe", "verbatim", "codemix"):
    b = stt_raw(CLIP, "pilot", fmt=fmt)
    print(f"\n===== {fmt} =====")
    print("fields:", *paths(b), sep="\n  ")
    print(json.dumps(short(b), ensure_ascii=False, indent=1))

print("\nWhat to look for: any field like confidence / score / probability / words / segments / alternatives.")
print("If only 'transcript' (+ ids/flags) comes back, there is no confidence to use, and the false REDs stay")
print("a documented limit: the controller says 'say again', which ICAO requires for any doubtful readback.")
