"""
Step 2b: run whole radio scenarios end to end - Timbre speaks, radio noise, Prisma hears, engine decides.

  python run_scenarios.py --dry-run            # perfect hearing (the scripted text): checks the scenarios themselves
  python run_scenarios.py                      # clean audio and 10 dB radio
  python run_scenarios.py --cond 10            # one condition

PASS rules (fixed before the run):
  - every expected alert appears at its step with its level
    (LATE = it came at a later step, e.g. only after the readback named the aircraft; shown with the delay.
     LATE is not a PASS - it is reported separately so nothing is rounded up)
  - NORMAL_DEL gives no RED at all
  - OTHER-RED = the expected alert did not come, but a different RED did at that step (shown which).
    It is NOT counted as a pass.
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
import sentinel_actions
from scenarios import SCENARIOS, VOICE
from sentinel_state import RunwayEngine
from sentinel_pipeline import hear
from radio_sim import radio


def run(name, sc, cond, dry, tts=None, stt=None, voice=False):
    import soundfile as sf
    eng = RunwayEngine(sc["airport"], sc["traffic"], sc["phases"])
    steps, prep = [], None
    if voice and tts:
        import sentinel_voice
        prep = sentinel_voice.prepare(tts, sc["airport"], sc["traffic"])   # before any call: not alert-time
    for i, (t, ch, spk, said) in enumerate(sc["steps"]):
        text2, lat, hinted, h = None, 0.0, False, {}
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
            h = hear(path, ch, sc["airport"], sc["traffic"], stt)
            text, text2, lat, hinted = h["text"], h["text2"], h["latency_s"], h["hinted"]
        e0 = time.perf_counter()
        rec = eng.call(t, ch, text, text2, hinted=hinted if not dry else False)
        eng_ms = (time.perf_counter() - e0) * 1000
        spoken = []
        if voice:
            import sentinel_voice
            al = sentinel_voice.pick(rec["alerts"])          # one voice per call: the most dangerous alert
            if al:
                phr = sentinel_voice.phrases(al)
                path = f"audio_alerts/out/{name}_{cond}_t{t}.wav"
                ms, dur, fb = sentinel_voice.assemble(phr, path)
                spoken.append({"file": path, "says": sentinel_voice.sentence(phr), "assemble_ms": round(ms, 1),
                               "duration_s": round(dur, 2), "fallback": fb,
                               "ready_after_call_s": round(lat + (eng_ms + ms) / 1000, 2)})
        steps.append({"t": t, "channel": ch, "speaker": spk, "said": said, "heard": text, "heard2": text2,
                      "hinted": hinted, "first_listen": h.get("first"),
                      "latency_s": round(lat, 2), "engine_ms": round(eng_ms, 1), "spoken": spoken,
                      "status": rec["analysis"]["status"],
                      "alerts": [{k: a[k] for k in ("level", "kind", "text")} for a in rec["alerts"]]})
    tail = eng.tick(sc["steps"][-1][0] + 15)
    misses, late = [], []
    for i, kind, lvl in sc.get("expect", []):
        hit = [j for j in range(i, len(steps)) if any(a["kind"] == kind and a["level"] == lvl for a in steps[j]["alerts"])]
        if not hit:
            other = [a["kind"] for a in steps[i]["alerts"] if a["level"] == "RED"]
            misses.append(f"step {i}: expected {lvl} {kind} - never came"
                          + (f" (a different RED did: {', '.join(other)})" if other else ""))
        elif hit[0] != i:
            late.append(f"step {i}: {lvl} {kind} came {steps[hit[0]]['t'] - steps[i]['t']} s late (at t={steps[hit[0]]['t']}s)")
    reds = [a for s in steps for a in s["alerts"] if a["level"] == "RED"] + [a for a in tail if a["level"] == "RED"]
    if sc.get("no_red") and reds:
        misses.append(f"normal traffic gave {len(reds)} RED alert(s)")
    return {"scenario": name, "cond": cond, "prepared_clips": prep, "pass": not misses and not late, "late": late, "misses": misses,
            "verdict": ("FAIL" if not any("a different RED did" in m for m in misses) else "OTHER-RED")
                       if misses else ("LATE" if late else "PASS"), "steps": steps,
            "end_alerts": [{k: a[k] for k in ("level", "kind", "text")} for a in tail]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cond", default="clean,10")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--voice", action="store_true", help="speak RED alerts from the pre-recorded clips + time it")
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
            r = run(name, sc, cond, a.dry_run, tts, stt, a.voice)
            out.append(r)
            print(f"\n=== {name} [{sc['airport']}] {r['verdict']} ===")
            for s in r["steps"]:
                print(f"  t={s['t']:>3}s {s['channel']:<7} {s['status']:<9} {s['heard']}"
                      + (f"   ({s['latency_s']} s)" if s["latency_s"] else ""))
                if s["heard2"]:
                    print(f"           second listen: {s['heard2']}")
                if s.get("hinted"):
                    print(f"           (hazard-word hint used; listen 1 was: {s['first_listen']})")
                for al in s["alerts"]:
                    print(f"           {'🔴' if al['level'] == 'RED' else '🟡' if al['level'] == 'AMBER' else 'ℹ️'} {al['text']}")
                for sp in s.get("spoken", []):
                    print(f"           🔊 \"{sp['says']}\"  ready {sp['ready_after_call_s']} s after the call "
                          f"(Prisma {s['latency_s']} s + engine {s['engine_ms']} ms + voice {sp['assemble_ms']} ms; "
                          f"plays {sp['duration_s']} s)" + (f"  [word-by-word fallback for: {sp['fallback']}]" if sp["fallback"] else ""))
            for al in r["end_alerts"]:
                print(f"  (after last call) {'🔴' if al['level'] == 'RED' else '🟡'} {al['text']}")
            for m in r["late"]:
                print(f"  .. {m}")
            for m in r["misses"]:
                print(f"  !! {m}")
    print("\n================ SUMMARY ================")
    for cond in conds:
        rs = [r for r in out if r["cond"] == cond]
        print(f"  {cond:<6} {sum(r['pass'] for r in rs)}/{len(rs)} on time: "
              + ", ".join(f"{r['scenario']}{'' if r['pass'] else ' ' + r['verdict']}" for r in rs))
    lats = [s["latency_s"] for r in out for s in r["steps"] if s["latency_s"]]
    if lats:
        lats.sort()
        print(f"  Prisma time per call: median {lats[len(lats) // 2]:.2f} s, worst {lats[-1]:.2f} s ({len(lats)} calls)")
    sp = [x for r in out for s in r["steps"] for x in s.get("spoken", [])]
    if sp:
        rd = sorted(x["ready_after_call_s"] for x in sp)
        am = sorted(x["assemble_ms"] for x in sp)
        print(f"  RED alert voice ready after the call ends: median {rd[len(rd) // 2]:.2f} s, worst {rd[-1]:.2f} s "
              f"({len(sp)} alerts; joining clips: median {am[len(am) // 2]:.1f} ms)")
        print("  (not included: detecting that the speaker has stopped talking, which a live system must add)")
    eng = sorted(s["engine_ms"] for r in out for s in r["steps"])
    print(f"  Engine decision time per call: median {eng[len(eng) // 2]:.1f} ms, worst {eng[-1]:.1f} ms")
    os.makedirs("results", exist_ok=True)
    path = f"results/scenarios_{'dry_' if a.dry_run else ''}{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()