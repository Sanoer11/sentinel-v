"""
Step 2b: run whole radio scenarios end to end - Timbre speaks, radio noise, Prisma hears, engine decides.

  python scripts/run_scenarios.py --dry-run            # perfect hearing (the scripted text): checks the scenarios themselves
  python scripts/run_scenarios.py                      # clean audio and 10 dB radio
  python scripts/run_scenarios.py --cond 10            # one condition
  python scripts/run_scenarios.py --cond 10 --seeds 5  # 5 DIFFERENT noise recordings at 10 dB (seed 0 = the old one)

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
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import glob
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


def noisy_path(clean, cond, seed):
    """seed 0 keeps the old file name, so earlier runs stay comparable; seed k>0 = a new noise recording."""
    return clean.replace(".wav", f"_snr{cond}.wav" if seed == 0 else f"_snr{cond}_n{seed}.wav")


# THE LOCKED EXAM, scenario part: the same 8 scenarios spoken by voices never used in any test or fix
# (Timbre v2.5 English set + the Marathi voice Ishaan, kept aside since Day 3). Run ONCE on frozen code.
# Hinglish exception: Poorvi is the only Hinglish voice that exists, so VEHICLE_HI is NOT an unseen voice - reported.
LOCKED_VOICE = {
    "tower": ("Pranav", "timbre-v2.5", "en-IN"),
    "p1": ("Kaveri", "timbre-v2.5", "en-IN"),
    "p2": ("Shlok", "timbre-v2.5", "en-IN"),
    "p3": ("Devika", "timbre-v2.5", "en-IN"),
    "veh_mr": ("Ishaan", "timbre-v2.5", "mr-IN"),
    "veh_hi": ("Poorvi", "timbre-v2.5", "hi-en"),
}
LOCKED_SEEDS = range(100, 105)          # noise recordings never used before

# OWN-VOICE TEST (A17 held-out check): the 33 scenario lines read by a real person, recorded on a phone/laptop,
# my_voice/scen/<SCENARIO>_<step>.m4a (or .wav/.mp3). Never uploaded or published (my_voice/ is gitignored).
# Run once on committed code: clean + 10 dB with noise recordings 300-304, never used before.
HUMAN_DIR, HUMAN_SEEDS = "my_voice/scen", range(300, 305)


def human_script():
    os.makedirs(HUMAN_DIR, exist_ok=True)
    lines = []
    for name, sc in SCENARIOS.items():
        for i, (t, ch, spk, said) in enumerate(sc["steps"]):
            lines.append(f"{name}_{i}.m4a   [{ch}, {spk}]   {said}")
    open(f"{HUMAN_DIR}/RECORD_THESE.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n{len(lines)} lines -> {HUMAN_DIR}/RECORD_THESE.txt")


def human_clip(name, i, spk, dest):
    """Your recording of this line, as 16 kHz mono WAV (ffmpeg, or macOS afconvert)."""
    import shutil, subprocess
    src = next((f"{HUMAN_DIR}/{name}_{i}.{e}" for e in ("m4a", "wav", "mp3") if os.path.exists(f"{HUMAN_DIR}/{name}_{i}.{e}")), None)
    if src is None:
        raise SystemExit(f"missing recording: {HUMAN_DIR}/{name}_{i}.m4a  (run  python scripts/run_scenarios.py --human-script)")
    if not os.path.exists(dest):
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", dest], check=True)
        else:
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", src, dest], check=True)
    return True


def run(name, sc, cond, dry, tts=None, stt=None, voice=False, seed=0, voices=None, folder="scen"):
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
            clean = f"audio_eval/{folder}/{name}_{i}_{spk}.wav"
            if folder == "scen_human":
                human_clip(name, i, spk, clean)
            else:
                v = (voices or VOICE)[spk]
                if not tts(said, v[0], v[1], v[2], clean):
                    raise SystemExit(f"TTS failed for {name} step {i}")
            path = clean
            if cond != "clean":
                path = noisy_path(clean, cond, seed)
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
                      "hint_text": h.get("hint_text"), "hint_rejected": h.get("hint_rejected", False),
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
    return {"scenario": name, "cond": cond, "seed": seed, "prepared_clips": prep, "pass": not misses and not late, "late": late, "misses": misses,
            "verdict": ("FAIL" if not any("a different RED did" in m for m in misses) else "OTHER-RED")
                       if misses else ("LATE" if late else "PASS"), "steps": steps,
            "end_alerts": [{k: a[k] for k in ("level", "kind", "text")} for a in tail]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cond", default="clean,10")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--seeds", type=int, default=1, help="noise recordings per noisy condition (clean has only one)")
    ap.add_argument("--seed-from", type=int, default=0, help="first noise recording number (5 = never heard before)")
    ap.add_argument("--locked", action="store_true", help="THE EXAM: unseen voices, clean + 10 dB x 5 new noise, ONCE")
    ap.add_argument("--voice", action="store_true", help="speak RED alerts from the pre-recorded clips + time it")
    ap.add_argument("--v25", action="store_true",
                    help="PRACTICE run with the exam's Timbre v2.5 voices (used up by the locked exam on 7 Nov, so now "
                         "allowed for development): 10 dB, noise recordings 200-209, never the exam's 100-104")
    ap.add_argument("--human-script", action="store_true", help="write the 33 lines to record (my_voice/scen/RECORD_THESE.txt)")
    ap.add_argument("--human", action="store_true",
                    help="OWN-VOICE TEST, once, on committed code: your recordings, clean + 10 dB x noise 300-304")
    a = ap.parse_args()
    if a.human_script:
        return human_script()
    if a.human:
        import run_eval
        commit, dirty = run_eval.git_state()
        if commit is None or dirty:
            raise SystemExit("STOP: the own-voice test needs committed code. Commit first (git status must be clean).")
        if glob.glob("results/scenarios_human_*.json"):
            raise SystemExit("STOP: the own-voice test was already run: " + glob.glob("results/scenarios_human_*.json")[0])
        missing = [f"{n}_{i}" for n, sc in SCENARIOS.items() for i in range(len(sc["steps"]))
                   if not any(os.path.exists(f"{HUMAN_DIR}/{n}_{i}.{e}") for e in ("m4a", "wav", "mp3"))]
        if missing:
            raise SystemExit(f"{len(missing)} recordings missing, e.g. {missing[:5]} (see {HUMAN_DIR}/RECORD_THESE.txt)")
        a.cond, a.seed_from, a.seeds = "clean,10", HUMAN_SEEDS.start, len(HUMAN_SEEDS)
    if a.v25:
        a.cond, a.seed_from, a.seeds = "10", 200, 10
    locked = a.locked and not a.dry_run
    if locked:
        import run_eval
        commit, dirty = run_eval.git_state()
        if commit is None or dirty:
            raise SystemExit("STOP: the exam needs committed code. Commit first (git status must be clean).")
        if "locked_scenarios" in run_eval.ledger():
            raise SystemExit(f"STOP: the scenario exam was already used on {run_eval.ledger()['locked_scenarios']['date']}.")
        a.cond, a.seed_from, a.seeds, a.voice = "clean,10", LOCKED_SEEDS.start, len(LOCKED_SEEDS), True
    conds = ["text"] if a.dry_run else a.cond.split(",")
    runs = [(c, k) for c in conds for k in (range(a.seed_from, a.seed_from + a.seeds) if c not in ("clean", "text") else [0])]
    tts = stt = None
    if not a.dry_run:
        from gnani_client import tts, stt
        n = sum(len(s["steps"]) for s in SCENARIOS.values())
        m = n * len(runs)
        print(f"{n} lines x {len(runs)} runs = {m} calls, about {m + m // 8} STT + {n} TTS, about Rs {0.05 * (m + m // 8 + n):.0f}.")
        if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
            return
    os.makedirs("audio_eval/scen", exist_ok=True)
    os.makedirs("audio_eval/scen_v25", exist_ok=True)
    os.makedirs("audio_eval/scen_human", exist_ok=True)
    out = []
    for cond, seed in runs:
        print(f"\n################ condition: {cond}{f'  noise recording {seed}' if seed else ''} ################")
        for name, sc in SCENARIOS.items():
            r = run(name, sc, cond, a.dry_run, tts, stt, a.voice, seed,
                    voices=LOCKED_VOICE if (locked or a.v25) else None,
                    folder="scen_locked" if locked else "scen_human" if a.human else "scen_v25" if a.v25 else "scen")
            out.append(r)
            print(f"\n=== {name} [{sc['airport']}] {r['verdict']} ===")
            for s in r["steps"]:
                print(f"  t={s['t']:>3}s {s['channel']:<7} {s['status']:<9} {s['heard']}"
                      + (f"   ({s['latency_s']} s)" if s["latency_s"] else ""))
                if s["heard2"]:
                    print(f"           second listen: {s['heard2']}")
                if s.get("hinted"):
                    print(f"           (hazard-word hint used; listen 1 was: {s['first_listen']})")
                elif s.get("hint_text"):
                    print(f"           (hint asked, NOT used{' - it lost the vehicle listen 1 heard' if s.get('hint_rejected') else ''}: {s['hint_text']})")
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
    for cond, seed in runs:
        rs = [r for r in out if r["cond"] == cond and r["seed"] == seed]
        print(f"  {cond:<6}{f' n{seed}' if seed else '   '} {sum(r['pass'] for r in rs)}/{len(rs)} on time: "
              + ", ".join(f"{r['scenario']}{'' if r['pass'] else ' ' + r['verdict']}" for r in rs))
    if a.seeds > 1:
        print("  --- per scenario, over all noise recordings (one noise recording = one sample, not a rate) ---")
        for cond in conds:
            if cond in ("clean", "text"):
                continue
            for name in SCENARIOS:
                rs = [r for r in out if r["cond"] == cond and r["scenario"] == name]
                v = [r["verdict"] for r in rs]
                print(f"  {cond:<6} {name:<14} PASS {v.count('PASS')}/{len(v)}"
                      + "".join(f", {x} {v.count(x)}" for x in ("LATE", "OTHER-RED", "FAIL") if v.count(x)))
            nr = [r for r in out if r["cond"] == cond and SCENARIOS[r["scenario"]].get("no_red")]
            bad = sum(any("normal traffic" in m for m in r["misses"]) for r in nr)
            print(f"  {cond:<6} normal traffic with a false RED: {bad}/{len(nr)} recordings")
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
    tag = 'locked_' if locked else 'dry_' if a.dry_run else 'human_' if a.human else 'v25_' if a.v25 else ''
    path = f"results/scenarios_{tag}{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {path}")
    if locked:
        import run_eval
        L = run_eval.ledger()
        L["locked_scenarios"] = {"date": f"{datetime.datetime.now():%Y-%m-%d %H:%M}", "git": run_eval.git_state()[0],
                                 "result_file": path, "voices": LOCKED_VOICE, "seeds": list(LOCKED_SEEDS)}
        json.dump(L, open("testsets/ledger.json", "w"), indent=1)
        print("Scenario exam is now USED. It can never be run as the exam again.")
        print("Note: VEHICLE_HI used Poorvi, the only Hinglish voice - NOT an unseen voice.")


if __name__ == "__main__":
    main()
