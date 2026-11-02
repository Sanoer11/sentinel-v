"""
Step 2b: run whole radio scenarios end to end - Timbre speaks, radio noise, Prisma hears, engine decides.

  python run_scenarios.py --dry-run            # perfect hearing (the scripted text): checks the scenarios themselves
  python run_scenarios.py                      # clean audio and 10 dB radio
  python run_scenarios.py --cond 10            # one condition

PASS rules (fixed before the run):
  - every expected alert appears at its step with its level
  - NORMAL_DEL gives no RED at all
  - a scenario whose step is FLAGGED by noise still counts as FAIL if its expected alert is missing:
    nothing is excused; the output shows why.
Latency: wall time of each Prisma call is logged (used in Step 3).
"""
import os
import sys
import json
import time
import hashlib
import argparse
import datetime

import sentinel_parse
from scenarios import SCENARIOS, VOICE
from sentinel_state import RunwayEngine
from radio_sim import radio


def hear(path, channel, airport, traffic, stt):
    """First listen + the verbatim second listen, by the same rules as run_eval."""
    t0 = time.perf_counter()
    text = stt(path, channel)
    lat = time.perf_counter() - t0
    first = sentinel_parse.extract(text, airport, set(traffic))
    text2 = None
    if (sentinel_parse.needs_second_listen(first)
            or (sentinel_parse.NINER_GLUE_FIX and sentinel_parse.needs_callsign_second_listen(first))
            or sentinel_parse.needs_vehicle_second_listen(first, set(traffic))):
        t1 = time.perf_counter()
        text2 = stt(path, channel, fmt="verbatim")
        lat += time.perf_counter() - t1
    return text, text2, lat


def run(name, sc, cond, dry, tts=None, stt=None):
    import soundfile as sf
    eng = RunwayEngine(sc["airport"], sc["traffic"], sc["phases"])
    steps = []
    for i, (t, ch, spk, said) in enumerate(sc["steps"]):
        text2, lat = None, 0.0
        if dry:
            text = said
        else:
            v = VOICE[spk]
            clean = f"audio_eval/scen/{name}_{i}_{spk}.wav"
            if not tts(said, v[0], v[1], v[2], clean):
                raise SystemExit(f"TTS failed for {name} step {i}")
            path = clean
            if cond != "clean":
                path = clean.replace(".wav", f"_snr{cond}.wav")
                if not os.path.exists(path):
                    x, sr = sf.read(clean)
                    sf.write(path, radio(x, sr, int(cond), seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)),
                             8000, subtype="PCM_16")
            text, text2, lat = hear(path, ch, sc["airport"], sc["traffic"], stt)
        rec = eng.call(t, ch, text, text2)
        steps.append({"t": t, "channel": ch, "speaker": spk, "said": said, "heard": text, "heard2": text2,
                      "latency_s": round(lat, 2), "status": rec["analysis"]["status"],
                      "alerts": [{k: a[k] for k in ("level", "kind", "text")} for a in rec["alerts"]]})
    tail = eng.tick(sc["steps"][-1][0] + 15)
    misses = [f"step {i}: expected {lvl} {kind}" for i, kind, lvl in sc.get("expect", [])
              if not any(a["kind"] == kind and a["level"] == lvl for a in steps[i]["alerts"])]
    reds = [a for s in steps for a in s["alerts"] if a["level"] == "RED"] + [a for a in tail if a["level"] == "RED"]
    if sc.get("no_red") and reds:
        misses.append(f"normal traffic gave {len(reds)} RED alert(s)")
    return {"scenario": name, "cond": cond, "pass": not misses, "misses": misses, "steps": steps,
            "end_alerts": [{k: a[k] for k in ("level", "kind", "text")} for a in tail]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cond", default="clean,10")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    conds = ["text"] if a.dry_run else a.cond.split(",")
    tts = stt = None
    if not a.dry_run:
        from gnani_client import tts, stt
        n = sum(len(s["steps"]) for s in SCENARIOS.values())
        print(f"{n} lines x {len(conds)} conditions = {n * len(conds)} STT (+ a few second listens) + {n} TTS, "
              f"about Rs {0.05 * (n * len(conds) + n):.0f}.")
        if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
            return
    os.makedirs("audio_eval/scen", exist_ok=True)
    out = []
    for cond in conds:
        print(f"\n################ condition: {cond} ################")
        for name, sc in SCENARIOS.items():
            r = run(name, sc, cond, a.dry_run, tts, stt)
            out.append(r)
            print(f"\n=== {name} [{sc['airport']}] {'PASS' if r['pass'] else 'FAIL'} ===")
            for s in r["steps"]:
                print(f"  t={s['t']:>3}s {s['channel']:<7} {s['status']:<9} {s['heard']}"
                      + (f"   ({s['latency_s']} s)" if s["latency_s"] else ""))
                if s["heard2"]:
                    print(f"           second listen: {s['heard2']}")
                for al in s["alerts"]:
                    print(f"           {'🔴' if al['level'] == 'RED' else '🟡' if al['level'] == 'AMBER' else 'ℹ️'} {al['text']}")
            for al in r["end_alerts"]:
                print(f"  (after last call) {'🔴' if al['level'] == 'RED' else '🟡'} {al['text']}")
            for m in r["misses"]:
                print(f"  !! {m}")
    print("\n================ SUMMARY ================")
    for cond in conds:
        rs = [r for r in out if r["cond"] == cond]
        print(f"  {cond:<6} {sum(r['pass'] for r in rs)}/{len(rs)} scenarios pass: "
              + ", ".join(f"{r['scenario']}{'' if r['pass'] else ' FAIL'}" for r in rs))
    lats = [s["latency_s"] for r in out for s in r["steps"] if s["latency_s"]]
    if lats:
        lats.sort()
        print(f"  Prisma time per call: median {lats[len(lats) // 2]:.2f} s, worst {lats[-1]:.2f} s ({len(lats)} calls)")
    os.makedirs("results", exist_ok=True)
    path = f"results/scenarios_{'dry_' if a.dry_run else ''}{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
