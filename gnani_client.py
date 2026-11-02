"""
Tiny Gnani API client (Timbre TTS + Prisma STT). Reads the key only when a call is made,
so tests and dry runs work without a key.
"""
import os
import json
import time
import requests

BASE = "https://api.vachana.ai"

# General ATC words only. NO flight numbers (they bias Prisma toward expected traffic).
KEYTERMS = sorted({
    "runway", "taxiway", "cleared to land", "cleared for takeoff", "line up and wait",
    "hold short", "cross runway", "report vacated", "niner", "tree", "fife", "IFLY",
    "Air India", "Akasa Air", "Follow Me", "Bird Chaser", "FOD", "Bravo", "Charlie",
    "tower", "holding point",
})
TOPIC = ("Air traffic control tower radio at an Indian airport: controller clearances, "
         "pilot readbacks with callsigns and runway numbers, and airside vehicle radio.")


def _key():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    k = os.environ.get("GNANI_API_KEY")
    if not k:
        raise SystemExit("GNANI_API_KEY missing. Put it in .env as GNANI_API_KEY=...")
    return k


def _post(url, **kw):
    headers = {"X-API-Key-ID": _key()}
    r = None
    for attempt in range(6):
        r = requests.post(url, headers=headers, timeout=60, **kw)
        if r.status_code != 429 and r.status_code < 500:
            return r
        # 429 = rate limit, 5xx = server hiccup (A4 got one 502): wait and try again
        print(f"  [{r.status_code} from server, retry {attempt + 1}]")
        time.sleep(1.5 * (attempt + 1))
    return r


def tts(text, voice, model, lang, path, speed=1.0):
    """Text -> 16 kHz mono WAV. Cached: never pays twice for the same file."""
    if os.path.exists(path):
        return True
    body = {"text": text, "voice": voice, "model": model, "language": lang, "speed": speed,
            "audio_config": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "wav"}}
    r = _post(f"{BASE}/api/v1/tts/inference", json=body)
    if r.status_code != 200:
        print(f"  TTS failed ({r.status_code}): {r.text[:200]}")
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(r.content)
    return True


def stt(path, channel, fmt="transcribe", previous_text=None, extra_keyterms=None):
    """Prisma v3.0 + general ATC context. fmt: transcribe (digits) | verbatim | codemix (words).
    previous_text: what was said just before (the tower's call, for a readback). Used ONLY by the
    context listen, which may fill gaps but never overrule the first, neutral listen."""
    data = {"model": "prisma-v3.0", "format": fmt,
            "language_code": "hi-IN,en-IN,mr-IN" if channel == "airside" else "en-IN",
            "keyterms": json.dumps(sorted(set(KEYTERMS) | set(extra_keyterms or [])), ensure_ascii=False), "topic": TOPIC}
    if previous_text:
        data["previous_text"] = previous_text
    with open(path, "rb") as f:
        r = _post(f"{BASE}/stt/v3", data=data,
                  files={"audio_file": (os.path.basename(path), f, "application/octet-stream")})
    try:
        b = r.json()
    except ValueError:
        return f"<error {r.status_code}>"
    return b.get("transcript", "") if b.get("success") else f"<error {b}>"