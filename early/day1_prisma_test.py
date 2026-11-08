"""
Sentinel-V — Day 1 experiment
Question this answers: can Prisma reliably hear ATC talk — callsigns and runway numbers?
If it can't, nothing else in the project matters. So we test this first.

What it does:
  1. Timbre speaks 11 realistic ATC / airside lines in different voices -> audio/*.wav
  2. Prisma v3.0 transcribes each line TWICE:
       A) plain
       B) with ATC context (keyterms + topic)  <- Prisma v3.0 feature built for domain words
  3. Checks whether the critical tokens (callsign digits, runway) were caught
  4. Saves everything to results.json

Setup:
  pip install requests python-dotenv
  create a file named .env with:  GNANI_API_KEY=your_key_here
  python early/day1_prisma_test.py
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative

import re
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ["GNANI_API_KEY"]
BASE = "https://api.vachana.ai"
HEADERS = {"X-API-Key-ID": KEY}
os.makedirs("audio", exist_ok=True)

# ---------------------------------------------------------------------------
# Test lines. Real ICAO style: digits spoken one by one, "niner" for 9.
# Real callsigns: IndiGo = "IFLY", Air India = "Air India", Vistara = "Vistara".
# Scenes mirror the real incidents: Mumbai 2024 (RWY 27) and Delhi 2023 (RWY 29R).
# Line 9 is a DELIBERATE wrong readback (pilot says 29L instead of 29R).
# ---------------------------------------------------------------------------
LINES = [
    # id, channel, voice, model, tts_lang, text, must_catch
    (1, "tower", "Avinash", "timbre-v3.0", "en-IN",
     "IFLY six zero five three, runway two seven, cleared to land, wind two seven zero degrees one two knots.",
     ["6053", "27"]),
    (2, "pilot", "Riyaa", "timbre-v3.0", "en-IN",
     "Cleared to land runway two seven, IFLY six zero five three.",
     ["6053", "27"]),
    (3, "tower", "Avinash", "timbre-v3.0", "en-IN",
     "Air India six five seven, line up and wait runway two seven.",
     ["657", "27"]),
    (4, "pilot", "Harshad", "timbre-v3.0", "en-IN",
     "Line up and wait runway two seven, Air India six five seven.",
     ["657", "27"]),
    (5, "tower", "Avinash", "timbre-v3.0", "en-IN",
     "Air India six five seven, runway two seven, cleared for takeoff.",
     ["657", "27"]),
    (6, "tower", "Prakash", "timbre-v3.0", "en-IN",
     "Vistara niner two six, cross runway two niner right, report vacated.",
     ["926", "29r"]),
    (7, "pilot", "Devansh", "timbre-v3.0", "en-IN",
     "Crossing runway two niner right, Vistara niner two six.",
     ["926", "29r"]),
    (8, "tower", "Prakash", "timbre-v3.0", "en-IN",
     "Vistara seven two five, runway two niner right, cleared for takeoff.",
     ["725", "29r"]),
    (9, "pilot", "Shubham", "timbre-v3.0", "en-IN",
     "Cleared for takeoff runway two niner left, Vistara seven two five.",
     ["725", "29l"]),
    (10, "airside", "Poorvi", "timbre-v2.5", "hi-en",
     "Tower, Follow Me One, runway two seven pe FOD check ke liye enter kar raha hoon, permission chahiye.",
     ["27"]),
    (11, "airside", "Ishaan", "timbre-v2.5", "mr-IN",
     "टॉवर, बर्ड चेसर टू, रनवे टू सेव्हन जवळ पक्षी आहेत, मी टॅक्सीवे ब्राव्होवर थांबलोय.",
     ["27"]),
]

# Prisma v3.0 context: words it should favour + what the audio is about
ATC_KEYTERMS = [
    "runway", "taxiway", "cleared to land", "cleared for takeoff", "line up and wait",
    "hold short", "cross runway", "report vacated", "niner", "IFLY", "Air India",
    "Vistara", "Akasa", "Follow Me", "Bird Chaser", "FOD", "Bravo", "tower",
]
ATC_TOPIC = ("Air traffic control tower radio at an Indian airport: controller clearances, "
             "pilot readbacks with callsigns and runway numbers, and airside vehicle radio.")


def post_with_retry(url, **kwargs):
    """Gnani can allow only 1 active request per account -> retry on 429."""
    for attempt in range(6):
        r = requests.post(url, headers=HEADERS, timeout=60, **kwargs)
        if r.status_code != 429:
            return r
        time.sleep(1.5 * (attempt + 1))
    return r


def tts(text, voice, model, lang, path):
    """Timbre: text -> 16 kHz mono WAV (16 kHz is what Prisma uses internally)."""
    if os.path.exists(path):
        return True  # cache: never pay twice for the same clip
    body = {
        "text": text, "voice": voice, "model": model, "language": lang, "speed": 1.0,
        "audio_config": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                         "encoding": "linear_pcm", "container": "wav"},
    }
    r = post_with_retry(f"{BASE}/api/v1/tts/inference", json=body)
    if r.status_code != 200:
        print(f"  TTS failed ({r.status_code}): {r.text[:200]}")
        return False
    with open(path, "wb") as f:
        f.write(r.content)
    return True


def stt(path, channel, with_context):
    """Prisma v3.0: WAV -> text. format=transcribe turns spoken numbers into digits."""
    data = {"model": "prisma-v3.0", "format": "transcribe",
            "language_code": "hi-IN,en-IN,mr-IN" if channel == "airside" else "en-IN"}
    if with_context:
        data["keyterms"] = json.dumps(ATC_KEYTERMS)
        data["topic"] = ATC_TOPIC
    with open(path, "rb") as f:
        r = post_with_retry(f"{BASE}/stt/v3",
                            files={"audio_file": (os.path.basename(path), f, "audio/wav")},
                            data=data)
    body = r.json()
    if not body.get("success"):
        return f"<error: {body}>"
    return body.get("transcript", "")


def caught(transcript, token):
    """Loose match: '6 0 5 3', '6053', 'two nine right' -> handled best-effort."""
    t = transcript.lower()
    t = t.replace("niner", "9").replace("right", "r").replace("left", "l")
    compact = re.sub(r"[\s\-,.]", "", t)
    return token.lower() in compact


def main():
    results, score = [], {"plain": 0, "context": 0, "total": 0}
    for lid, ch, voice, model, lang, text, must in LINES:
        path = f"audio/line{lid:02d}_{ch}.wav"
        print(f"\n[{lid}] {ch.upper()} ({voice}) -> {text}")
        if not tts(text, voice, model, lang, path):
            continue
        plain = stt(path, ch, with_context=False)
        ctx = stt(path, ch, with_context=True)
        p_ok = [tok for tok in must if caught(plain, tok)]
        c_ok = [tok for tok in must if caught(ctx, tok)]
        score["plain"] += len(p_ok)
        score["context"] += len(c_ok)
        score["total"] += len(must)
        print(f"  plain   : {plain}   caught {p_ok}/{must}")
        print(f"  context : {ctx}   caught {c_ok}/{must}")
        results.append({"id": lid, "channel": ch, "voice": voice, "text": text,
                        "must_catch": must, "plain": plain, "context": ctx,
                        "plain_caught": p_ok, "context_caught": c_ok})

    with open("early/results.json", "w", encoding="utf-8") as f:
        json.dump({"score": score, "lines": results}, f, ensure_ascii=False, indent=2)

    t = score["total"] or 1
    print("\n================ RESULT ================")
    print(f"Critical tokens caught  plain  : {score['plain']}/{t}  ({100*score['plain']/t:.0f}%)")
    print(f"Critical tokens caught  context: {score['context']}/{t}  ({100*score['context']/t:.0f}%)")
    print("Line 9 is a wrong readback (29L vs 29R) — tomorrow's code must flag it.")
    print("Now check your credit balance on the dashboard and note how much this run cost.")


if __name__ == "__main__":
    main()