"""
Export the measured runs for the public site (web/). Run on the Mac, after the scenario runs:

  python export_web.py

Writes:
  web/public/data/summary.json          numbers, per-scenario outcome counts, latency list, readback check, runway layout
  web/public/data/runs/<SCENARIO>.json  every run of that scenario: each call (said / heard / verdict / alerts / runway picture)
  web/public/audio/*.mp3                the radio audio of each call + each spoken alert (all synthetic: Gnani Timbre)

Only SYNTHETIC audio is ever published: radio clips come from audio_eval/scen/ (Timbre voices + simulated radio) and
alerts are assembled from the Timbre phrase clips. Nothing from my_voice/ (friends' recordings) is read here.
The site is static: it never calls Prisma or Timbre and holds no API key.

Which runs: the latest clean run, plus every 10 dB run with noise recordings 0-19 (the same files as the results).
Transcripts are replayed through the current (frozen) engine, exactly like build_dashboard.py and exp_a12.py.
"""
import os
import sys
import glob
import json
import shutil
import datetime
import statistics
import subprocess
from collections import Counter

import build_dashboard as bd
from scenarios import SCENARIOS

WEB = "web/public"
NOISY_FILES = ["results/scenarios_20261104_035008.json", "results/scenarios_20261104_035839.json",
               "results/scenarios_20261104_040957.json", "results/scenarios_20261105_022236.json"]
READBACK_FILES = ["results/dev_20261031_000600.json", "results/dev2_20261031_004232.json",
                  "results/step1_20261031_013014.json"]
REAL = {"DEL_2023", "BOM_2024"}


def pick_encoder():
    """mp3 is ~8x smaller than wav. soundfile can write it (libsndfile >= 1.1); else ffmpeg; else plain wav."""
    try:
        import soundfile as sf
        if "MP3" in sf.available_formats():
            def enc(src, rel_base, out):
                x, sr = sf.read(src)
                rel = f"{rel_base}.mp3"
                sf.write(f"{out}/{rel}", x, sr, format="MP3")
                return rel
            return enc, "mp3 (soundfile)"
    except Exception:
        pass
    if shutil.which("ffmpeg"):
        def enc(src, rel_base, out):
            rel = f"{rel_base}.mp3"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-b:a", "32k", f"{out}/{rel}"], check=True)
            return rel
        return enc, "mp3 (ffmpeg)"
    return bd._copy_wav, "wav (no mp3 encoder found: install ffmpeg to make the site ~8x lighter)"


def latest_clean():
    files = sorted(f for f in glob.glob("results/scenarios_2026*.json") if "dry" not in f and "locked" not in f)
    for f in reversed(files):
        runs = [r for r in json.load(open(f, encoding="utf-8")) if r["cond"] == "clean"]
        if len(runs) == len(SCENARIOS):
            return f, runs
    return None, []


def git_hash():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def main():
    noisy_files = [f for f in sys.argv[1:] if f.endswith(".json")] or NOISY_FILES
    for f in noisy_files:
        if not os.path.isfile(f):
            raise SystemExit(f"Missing {f} - run this on the machine that has the scenario results.")
    clean_file, clean = latest_clean()
    noisy = [r for f in noisy_files for r in json.load(open(f, encoding="utf-8")) if r["cond"] != "clean"]
    seen, runs = set(), []
    for r in clean + noisy:
        k = (r["scenario"], r["cond"], r.get("seed", 0))
        if k not in seen:
            seen.add(k)
            runs.append(r)
    print(f"{len(runs)} runs: clean from {clean_file}, 10 dB from {len(noisy_files)} files")

    shutil.rmtree(f"{WEB}/audio", ignore_errors=True)
    shutil.rmtree(f"{WEB}/data", ignore_errors=True)
    os.makedirs(f"{WEB}/audio", exist_ok=True)
    os.makedirs(f"{WEB}/data/runs", exist_ok=True)
    enc, how = pick_encoder()
    print(f"audio: {how}")

    voice_ok, tts = False, None
    try:
        import sentinel_voice
        from gnani_client import tts
        for name in SCENARIOS:
            sc = SCENARIOS[name]
            sentinel_voice.prepare(tts, sc["airport"], sc["traffic"])     # cached: only missing phrase clips cost a TTS call
        voice_ok = True
    except (Exception, SystemExit) as e:
        print(f"  (alert voices skipped: {str(e)[:100]})")

    data = [bd.replay(r, voice_ok, tts, out=WEB, media=enc)
            for r in sorted(runs, key=lambda r: (r["scenario"], r["cond"] != "clean", r.get("seed", 0)))]
    order = list(bd.DESC)
    for name in order:
        mine = [d for d in data if d["scenario"] == name]
        json.dump(mine, open(f"{WEB}/data/runs/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    noisy_d = [d for d in data if d["cond"] != "clean"]
    lat = sorted(s["latency"] for d in data for s in d["steps"] if s["latency"])
    normal = [d for d in noisy_d if SCENARIOS[d["scenario"]].get("no_red")]
    import exp_a12
    rb = Counter()
    if all(os.path.isfile(f) for f in READBACK_FILES):
        rb = exp_a12.readback_tally(READBACK_FILES)
    summary = {
        "generated": f"{datetime.datetime.now():%d %b %Y}",
        "git": git_hash(),
        "stats": {
            "noisy_runs": len(noisy_d),
            "noisy_on_time": sum(d["verdict"] == "ON TIME" for d in noisy_d),
            "noisy_late": sum(d["verdict"] == "LATE" for d in noisy_d),
            "noise_samples": len({d["seed"] for d in noisy_d}),
            "normal_runs": len(normal),
            "false_red": sum(d["false_red"] for d in normal),
            "prisma_median": round(statistics.median(lat), 2) if lat else None,
            "prisma_p90": round(lat[int(0.9 * (len(lat) - 1))], 2) if lat else None,
            "alert_ready_median": None,
            "calls": len(lat),
        },
        "latency": [round(x, 2) for x in lat],
        "readback": {"wrong": {k[1]: v for k, v in rb.items() if k[0] == "WRONG"},
                     "correct": {k[1]: v for k, v in rb.items() if k[0] == "correct"}},
        "scenarios": [{
            "id": name, "where": bd.DESC[name][0], "what": bd.DESC[name][1], "airport": SCENARIOS[name]["airport"],
            "real": name in REAL, "no_red": bool(SCENARIOS[name].get("no_red")),
            "counts": {"clean": dict(Counter(d["verdict"] for d in data if d["scenario"] == name and d["cond"] == "clean")),
                       "noisy": dict(Counter(d["verdict"] for d in noisy_d if d["scenario"] == name))},
        } for name in order],
        "geo": {ap: {"name": bd.AIRPORTS[ap]["name"], "strips": [f"{a}/{b}" for a, b in bd.STRIPS[ap]],
                     "cross": [list(x) for x in bd.INTERSECTING.get(ap, [])]} for ap in bd.STRIPS},
    }
    json.dump(summary, open(f"{WEB}/data/summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(p) for p in glob.glob(f"{WEB}/audio/*")) / 1e6
    s = summary["stats"]
    print(f"Wrote {WEB}/data (8 scenario files + summary) and {len(os.listdir(f'{WEB}/audio'))} audio files ({size:.1f} MB)")
    print(f"10 dB: {s['noisy_on_time']}/{s['noisy_runs']} on time, {s['noisy_late']} late | normal traffic false RED "
          f"{s['false_red']}/{s['normal_runs']} | Prisma median {s['prisma_median']} s | readback wrong missed "
          f"{summary['readback']['wrong'].get('MATCH', 0)}")
    if not voice_ok:
        print("NOTE: no alert voices in this export. Run it where the API key and soundfile are available.")


if __name__ == "__main__":
    sys.exit(main())
