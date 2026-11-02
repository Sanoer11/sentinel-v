"""
Sentinel-V Step 3 — the alert voice.

Only RED alerts are spoken (amber stays on screen; Step 4 decides levels). The voice must be
FAST, so nothing is synthesised at alert time: every word an alert can need is recorded once
with Timbre (about 40 short clips) and an alert is assembled by joining clips - milliseconds.

Spoken form follows radio habit: headline first, then where, then who.
  "Runway conflict - runway two niner right - Vistara niner two six - and - Vistara seven two five"
Digits use ICAO radio words (tree, fife, niner) - the words controllers are trained to hear.

  python sentinel_voice.py --build     # record the single-word fallback clips once (~40 TTS calls, about Rs 2)
  Phrase clips (runways of an airport, callsigns on frequency) are recorded by prepare() before alerts happen.
"""
import os
import re
import time
import numpy as np

VOICE = ("Devansh", "timbre-v3.0", "en-IN")     # one fixed alert voice, different from all scenario speakers
SPEED = 0.9            # 3 Nov listening check: speed 1.0 was "a tiny bit fast"; niner and fife judged clear
SPEED = float(os.environ.get("SENTINEL_ALERT_SPEED", "1.0"))
SEG_DIR = f"audio_alerts/segments_x{SPEED:g}"      # one folder per speaking speed, so sets never mix
SR = 16000

HEADLINE = {
    "RUNWAY_CONFLICT": "Runway conflict",
    "READBACK_CONFLICT": "Readback conflict",
    "READBACK_MISMATCH": "Readback mismatch",
    "STOP_NOT_CONFIRMED": "Stop not confirmed",
    "GO_AROUND_NOT_CONFIRMED": "Go around not confirmed",
    "HOLD_SHORT_NOT_CONFIRMED": "Hold short not confirmed",
    "NO_READBACK": "No readback",
    "BIRDS_ON_ACTIVE_RUNWAY": "Birds reported",
    "INCURSION": "Runway incursion",
}
WORDS = {"runway": "runway", "and": "and", "confirm": "confirm", "unidentified": "unidentified aircraft",
         "L": "left", "R": "right", "C": "centre"}
DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "tree", "4": "four", "5": "fife",
          "6": "six", "7": "seven", "8": "eight", "9": "niner"}
NAMES = {"IGO": "IFLY", "AIC": "Air India", "AKJ": "Akasa Air", "VTI": "Vistara",
         "FOLLOWME": "Follow Me", "BIRDCHASER": "Bird Chaser"}


def all_segments():
    seg = {f"h_{k}": v for k, v in HEADLINE.items()}
    seg.update({f"w_{k}": v for k, v in WORDS.items()})
    seg.update({f"d_{k}": v for k, v in DIGITS.items()})
    seg.update({f"n_{k}": v for k, v in NAMES.items()})
    return seg


def word_path(key):
    return f"{SEG_DIR}/{key}_s{SPEED}.wav"


def build(tts):
    os.makedirs(SEG_DIR, exist_ok=True)
    made, took = 0, []
    for key, text in all_segments().items():
        path = word_path(key)
        if not os.path.exists(path):
            t0 = time.perf_counter()
            if not tts(text, VOICE[0], VOICE[1], VOICE[2], path, speed=SPEED):
                raise SystemExit(f"TTS failed for '{text}'")
            took.append(time.perf_counter() - t0)
            made += 1
    if took:
        took.sort()
        print(f"Timbre time per clip: median {took[len(took) // 2]:.2f} s, worst {took[-1]:.2f} s "
              f"- the delay a live (not pre-recorded) alert would add")
    return made


def say_callsign(cs):
    if not cs or cs.startswith("UNIDENTIFIED"):
        return WORDS["unidentified"]
    for code in ("FOLLOWME", "BIRDCHASER"):
        if cs.startswith(code):
            return " ".join([NAMES[code]] + [DIGITS[c] for c in cs[len(code):]])
    return " ".join([NAMES.get(cs[:3], cs[:3])] + [DIGITS[c] for c in cs[3:] if c.isdigit()])


def say_runway(rw):
    # no word "runway": every headline that is followed by a runway already says it ("Runway conflict, two niner right")
    return " ".join([DIGITS[c] for c in rw if c.isdigit()] + [WORDS[c] for c in rw if c in "LRC"])


# ONE spoken alert per radio call: the most dangerous one. The others stay on screen.
# (3 Nov run: a hold-short read back as "crossing" gave two spoken alerts back to back, 18 s of audio.)
PRIORITY = ["RUNWAY_CONFLICT", "INCURSION", "READBACK_CONFLICT", "HOLD_SHORT_NOT_CONFIRMED", "BIRDS_ON_ACTIVE_RUNWAY",
            "STOP_NOT_CONFIRMED", "GO_AROUND_NOT_CONFIRMED", "READBACK_MISMATCH", "NO_READBACK"]


def _head(alert):
    k = alert["kind"]
    if k == "RUNWAY_CONFLICT":
        return "READBACK_CONFLICT" if alert["text"].startswith("IF ") else "RUNWAY_CONFLICT"
    if k == "READBACK_INCOMPLETE":
        if "HOLD SHORT not confirmed" in alert["text"]:
            return "HOLD_SHORT_NOT_CONFIRMED"
        return "GO_AROUND_NOT_CONFIRMED" if "GO_AROUND" in alert["text"] else "STOP_NOT_CONFIRMED"
    return k


def phrases(alert):
    """The spoken alert as a list of phrases, or None if this alert is not spoken."""
    if alert["level"] != "RED":
        return None
    head, cs, rw = _head(alert), alert["callsigns"], alert["rw"]
    if head not in HEADLINE:
        return None
    # 3 Nov run: naming both aircraft made alerts 8-9 s long. The voice only has to say WHAT and WHERE and the
    # ONE aircraft the controller must act on now (the one just cleared / the one that read back wrong).
    # The other aircraft is on the screen. Target: under 5 s.
    out = [HEADLINE[head]]
    if head in ("RUNWAY_CONFLICT", "READBACK_CONFLICT", "INCURSION", "HOLD_SHORT_NOT_CONFIRMED"):
        out += ([say_runway(rw)] if rw else []) + [say_callsign(cs[0] if cs else None)]
    elif head == "BIRDS_ON_ACTIVE_RUNWAY":
        out += ([say_runway(rw)] if rw else []) + ([say_callsign(cs[-1])] if cs else [])
    elif head == "READBACK_MISMATCH":
        out += [say_callsign(cs[0] if cs else None), "confirm"]
    else:
        out += [say_callsign(cs[0] if cs else None)]
    return out


def pick(alerts):
    """The one alert of a call that gets the voice."""
    spoken = [a for a in alerts if phrases(a)]
    return min(spoken, key=lambda a: PRIORITY.index(_head(a))) if spoken else None


# ---------------------------------------------------------------- clips
# Callsigns are known in advance (flight plans / the traffic list) and runways are fixed per airport,
# so whole PHRASES are recorded before any alert: natural speech, and nothing is synthesised at alert time.
# Single-word clips are only the fallback for an aircraft that was not prepared.

def clip_path(text):
    import hashlib
    return f"{SEG_DIR}/p_{hashlib.md5(f'{text}|{VOICE}|{SPEED}'.encode()).hexdigest()[:12]}.wav"


def prepare(tts, airport, traffic):
    """Record the phrase clips this airport and this traffic can need. Returns (new clips, seconds)."""
    from sentinel_state import STRIPS
    want = list(HEADLINE.values()) + ["confirm", WORDS["unidentified"]]
    want += [say_runway(r) for pair in STRIPS[airport] for r in pair]
    want += [say_callsign(c) for c in traffic]
    os.makedirs(SEG_DIR, exist_ok=True)
    made, t0 = 0, time.perf_counter()
    for text in want:
        if not os.path.exists(clip_path(text)):
            if not tts(text, VOICE[0], VOICE[1], VOICE[2], clip_path(text), speed=SPEED):
                raise SystemExit(f"TTS failed for '{text}'")
            made += 1
    return made, time.perf_counter() - t0


def _word_fallback(text):
    seg = {v: k for k, v in all_segments().items()}
    if text in seg:                                   # a headline or name recorded as one clip
        return [word_path(seg[text])]
    keys = []
    for w in text.replace("Air India", "Air_India").replace("Akasa Air", "Akasa_Air") \
                 .replace("Follow Me", "Follow_Me").replace("Bird Chaser", "Bird_Chaser").split():
        w = w.replace("_", " ")
        if w in seg:
            keys.append(seg[w])
    return [word_path(k) for k in keys]


def _trim(x, thr=0.02):
    idx = np.where(np.abs(x) > thr * (np.max(np.abs(x)) + 1e-9))[0]
    return x[max(0, idx[0] - 160): idx[-1] + 160] if len(idx) else x


_cache = {}


def _load(path):
    import soundfile as sf
    if path not in _cache:
        x, sr = sf.read(path)
        if x.ndim > 1:
            x = x.mean(axis=1)
        assert sr == SR, f"{path} is {sr} Hz"
        _cache[path] = _trim(x)
    return _cache[path]


def assemble(phr, out_path):
    """Join the clips into one alert WAV. Returns (milliseconds taken, seconds of audio, phrases that used the
    slow word-by-word fallback). The milliseconds are the whole alert-time cost."""
    import soundfile as sf
    t0 = time.perf_counter()
    parts, fallback = [], []
    for i, text in enumerate(phr):
        p = clip_path(text)
        if os.path.exists(p):
            parts.append(_load(p))
        else:
            fallback.append(text)
            for w in _word_fallback(text):
                parts += [_load(w), np.zeros(int(0.04 * SR))]
        parts.append(np.zeros(int((0.25 if i == 0 else 0.12) * SR)))
    y = np.concatenate(parts)
    y = 0.9 * y / (np.max(np.abs(y)) + 1e-9)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, y, SR, subtype="PCM_16")
    return (time.perf_counter() - t0) * 1000, len(y) / SR, fallback


def sentence(phr):
    return ", ".join(phr)


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    if "--build" in sys.argv:
        from gnani_client import tts
        n = build(tts)
        print(f"Recorded {n} new clips ({len(all_segments())} in total) in {SEG_DIR}/ with voice {VOICE[0]}.")