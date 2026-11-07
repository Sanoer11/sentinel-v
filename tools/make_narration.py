"""Narration for the 2-minute film: 13 lines, Gnani Timbre v3.0 voice Shubham. Run from anywhere: python tools/make_narration.py
Writes film_vo/vo01.wav ... vo13.wav (wav files are gitignored and blocked by the hook)."""
import os, sys, json, wave
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for line in open(".env"):
    if line.strip().startswith("GNANI_API_KEY="):
        os.environ["GNANI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
import gnani_client as g
LINES = {
 "vo01": "Twenty-five seconds later, the same runway went to a second aircraft.",
 "vo03": "Sentinel-V listens to tower and airside radio, tracks who holds each runway, and speaks up before two clearances collide.",
 "vo04": "Delhi, Mumbai and Pune. English from the tower; Hindi, Hinglish and Marathi from the vehicles.",
 "vo05": "Here are the real Delhi calls, exactly as Gnani Prisma heard them.",
 "vo06": "Every call is understood, checked against its readback, and placed on the runway map.",
 "vo07": "Prisma hears a call in about half a second. The alert follows in milliseconds.",
 "vo08": "Every number on the site is measured, not estimated.",
 "vo09": "Then a locked exam, on voices it had never heard. Not one wrong readback missed.",
 "vo10": "The alert is ready within five milliseconds of a call being heard. Rules, not guesses: the same words always give the same verdict.",
 "vo12": "A second pair of ears for the tower. Listening to every call.",
 "vo13": "Sentinel-V is live right now. Scan the code, and replay the Delhi incident yourself.",
}
only = sys.argv[1:] or list(LINES)
out = "film_vo"; os.makedirs(out, exist_ok=True)
for k in only:
    path = f"{out}/{k}.wav"
    if os.path.exists(path):
        continue
    for sr in (24000, 16000):
        body = {"text": LINES[k], "voice": "Shubham", "model": "timbre-v3.0", "language": "en-IN", "speed": 0.95,
                "audio_config": {"sample_rate": sr, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}}
        r = g._post(f"{g.BASE}/api/v1/tts/inference", json=body)
        if r.status_code == 200 and r.content[:4] == b"RIFF":
            open(path, "wb").write(r.content)
            with wave.open(path) as w:
                print(k, sr, w.getframerate(), round(w.getnframes() / w.getframerate(), 2), "s")
            break
        print(k, sr, "failed", r.status_code, r.text[:150])
