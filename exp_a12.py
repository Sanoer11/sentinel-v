"""
Experiment A12 (FREE - no API calls): two fixes for DEL_2023 at 10 dB (failed 2 of 5 noise recordings).

  Fix T  "Taxiway 2 niner right, cleared for takeoff" -> runway (sentinel_actions.TAXIWAY_AS_RUNWAY)
  Fix L  a tower clearance whose runway number was lost ("runway 290, right. Cleared for takeoff") is kept,
         and the readback LOCATES it (as for a lost side), and goes into the runway picture
         (sentinel_state: rw_unknown / located)

Everything below re-uses transcripts already saved. RULES - FIXED NOW, before the run:
  (4 Nov later: Fix V = EXCLUDE_BY_NUMBER added to the same L1-L3 checks; Fix T removed from them.)
  T1. Fix T, every saved tower/pilot transcript (dev, dev2, step1): 0 lines worse, 0 new WRONG, >= 1 better
  L1. readback check (eval_readback logic): wrong readbacks missed stays 0
  L2. correct readbacks shown RED (false alarms) does not go up
  L3. every saved 10 dB / clean scenario run replayed through the new engine: 0 false RED in normal traffic,
      and no scenario that passed before fails now
  All hold -> both stay ON (they are on in the code now). Any fails -> the script says which to switch off.

Run:   python exp_a12.py results/dev_*.json results/dev2_*.json results/step1_*.json

RESULT (4 Nov): T1 FAIL (0 better; 0 worse) -> Fix T OFF. L1, L2, L3 PASS -> Fix L ON.

PART T2 - Fix T on audio never heard before. RULE FIXED NOW, before that run:
  run   python run_scenarios.py --cond 10 --seeds 5 --seed-from 5      (noise recordings 5-9: new)
  then  python exp_a12.py --taxiway results/scenarios_<that run>.json
  Fix T goes ON only if, replaying THOSE transcripts with Fix T off vs on (Fix L on in both):
    >= 1 scenario FAIL -> PASS, 0 PASS -> FAIL, 0 false RED in normal traffic.
"""
import sys
import json
import glob
from collections import Counter

import sentinel_actions
import sentinel_state
from scoring import judge_full, phases_of
from scenarios import SCENARIOS

RANK = {"OK": 3, "AMBER": 2, "FLAG": 1, "WRONG": 0}


def set_fixes(on):
    sentinel_actions.TAXIWAY_AS_RUNWAY = False         # Fix T is OFF (T1, T2): never part of these checks again
    sentinel_state.LOCATE_FROM_READBACK = on
    sentinel_state.EXCLUDE_BY_NUMBER = on
    # (left ON at the end of the free checks only for the verdict print; the module defaults are what count)


def part_t(files):
    better, worse, new_wrong, n = [], [], [], 0
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if res.get("testset") == "locked":
            raise SystemExit("Refusing: that is the LOCKED exam.")
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        its = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            it = its[r["id"]]
            if it["channel"] == "airside":
                continue
            n += 1
            sentinel_actions.TAXIWAY_AS_RUNWAY = False; o1 = judge_full(it, r["heard"], r.get("heard2"), r.get("hinted", False))[0]
            sentinel_actions.TAXIWAY_AS_RUNWAY = True;  o2 = judge_full(it, r["heard"], r.get("heard2"), r.get("hinted", False))[0]
            sentinel_actions.TAXIWAY_AS_RUNWAY = False
            tag = f"{res['testset']}:{r['id']}:{r['cond']}"
            if RANK[o2] > RANK[o1]:
                better.append((tag, o1, o2, r["heard"]))
            elif RANK[o2] < RANK[o1]:
                worse.append((tag, o1, o2, r["heard"]))
                if o2 == "WRONG":
                    new_wrong.append(tag)
    print("\n================ T: 'taxiway' read as runway ================")
    for tag, o1, o2, h in better + worse:
        print(f"  {'+' if RANK[o2] > RANK[o1] else '!!'} {tag:<24} {o1} -> {o2}   {h}")
    print(f"T: {n} tower/pilot transcripts | better {len(better)} | worse {len(worse)} | new WRONG {len(new_wrong)}")
    return bool(better) and not worse and not new_wrong


def readback_tally(files):
    """Same pairing and truth as eval_readback.py (so the numbers are comparable with its 4 Nov output)."""
    tally = Counter()
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        items = {it["id"]: it for it in ts["items"]}
        got = {(r["id"], r["cond"]): r for r in res["results"]}
        for (iid, cond), rb in got.items():
            it = items[iid]
            if it["channel"] != "pilot" or (iid[:-1] + "a", cond) not in got:
                continue
            tw = got[(iid[:-1] + "a", cond)]
            ph = {**(phases_of(items[iid[:-1] + "a"]) or {}), **(phases_of(it) or {})}
            e = sentinel_state.RunwayEngine(it["airport"], it["traffic"], ph)
            e.call(0, "tower", tw["heard"], tw.get("heard2"))
            e.call(4, "pilot", rb["heard"], rb.get("heard2"))
            p = e.pending[-1] if e.pending else None
            verdict = (p.get("verdict") or "UNMATCHED") if p else "NO_CLEARANCE"
            wrong_rb = it["truth"]["callsign"] not in it["traffic"] or any(t.startswith("wrong_readback") for t in it["traps"])
            tally[("WRONG" if wrong_rb else "correct", verdict)] += 1
    return tally


def part_l(files):
    print("\n================ L: readback check, before vs after ================")
    set_fixes(False); before = readback_tally(files)
    set_fixes(True);  after = readback_tally(files)
    for k in sorted(set(before) | set(after)):
        print(f"  {k[0]:>7} readback -> {k[1]:<5}  before {before[k]:>4}   after {after[k]:>4}")
    missed_b, missed_a = before[("WRONG", "MATCH")], after[("WRONG", "MATCH")]
    fr_b, fr_a = before[("correct", "MISMATCH")], after[("correct", "MISMATCH")]
    print(f"L1 wrong readbacks missed (MATCH): before {missed_b}, after {missed_a} | "
          f"L2 correct readbacks shown RED (MISMATCH): before {fr_b}, after {fr_a}")
    return missed_a == 0, fr_a <= fr_b


def replay(run):
    sc = SCENARIOS[run["scenario"]]
    eng = sentinel_state.RunwayEngine(sc["airport"], sc["traffic"], sc["phases"])
    steps = [eng.call(s["t"], s["channel"], s["heard"], s["heard2"], hinted=s.get("hinted", False))["alerts"]
             for s in run["steps"]]
    tail = eng.tick(run["steps"][-1]["t"] + 15)
    misses = [1 for i, kind, lvl in sc.get("expect", [])
              if not any(a["kind"] == kind and a["level"] == lvl for j in range(i, len(steps)) for a in steps[j])]
    late = [1 for i, kind, lvl in sc.get("expect", [])
            if not any(a["kind"] == kind and a["level"] == lvl for a in steps[i])]
    reds = sum(a["level"] == "RED" for al in steps for a in al) + sum(a["level"] == "RED" for a in tail)
    false_red = bool(sc.get("no_red") and reds)
    return ("FAIL" if misses or false_red else "LATE" if late else "PASS"), false_red


def part_s():
    print("\n================ S: every saved scenario run, replayed ================")
    runs = [r for f in sorted(glob.glob("results/scenarios_2026*.json")) if "dry" not in f
            for r in json.load(open(f, encoding="utf-8"))]
    flipped_bad, flipped_good, false_red = [], [], 0
    for r in runs:
        set_fixes(False); v1, _ = replay(r)
        set_fixes(True);  v2, fr = replay(r)
        false_red += fr
        tag = f"{r['scenario']} {r['cond']} n{r.get('seed', 0)}"
        if v1 == "PASS" and v2 != "PASS":
            flipped_bad.append((tag, v1, v2))
        if v1 != "PASS" and v2 == "PASS":
            flipped_good.append((tag, v1, v2))
    for tag, v1, v2 in flipped_good + flipped_bad:
        print(f"  {'+' if v2 == 'PASS' else '!!'} {tag:<28} {v1} -> {v2}")
    print(f"S: {len(runs)} saved scenario runs | now pass {len(flipped_good)} | now fail {len(flipped_bad)} | "
          f"false RED in normal traffic {false_red}")
    print("  (replay uses each run's saved transcripts; old runs heard by older code may differ in WHICH listens exist)")
    return not flipped_bad and false_red == 0


def part_t2(path):
    runs = [r for r in json.load(open(path, encoding="utf-8")) if r.get("seed", 0) >= 5]
    if not runs:
        raise SystemExit("No noise recordings 5+ in that file: run  python run_scenarios.py --cond 10 --seeds 5 --seed-from 5")
    sentinel_state.LOCATE_FROM_READBACK = True
    good = bad = fr = 0
    print("\n================ T2: Fix T on noise recordings 5-9 (never heard before) ================")
    for r in runs:
        sentinel_actions.TAXIWAY_AS_RUNWAY = False; v1, _ = replay(r)
        sentinel_actions.TAXIWAY_AS_RUNWAY = True;  v2, f2 = replay(r)
        fr += f2
        if v1 != v2:
            print(f"  {'+' if v2 == 'PASS' else '!!'} {r['scenario']} n{r['seed']}: {v1} -> {v2}")
        good += v1 != "PASS" and v2 == "PASS"
        bad += v1 == "PASS" and v2 != "PASS"
    sentinel_actions.TAXIWAY_AS_RUNWAY = False
    print(f"T2: {len(runs)} runs | FAIL->PASS {good} | PASS->FAIL {bad} | false RED in normal traffic {fr}")
    print("T2 VERDICT:", "PASS - set TAXIWAY_AS_RUNWAY = True in sentinel_actions.py" if good and not bad and not fr
          else "FAIL - stays OFF")


def part_fresh(path):
    """RULE (fixed 4 Nov, before the run): on noise recordings 10-14 (never heard), Fix L + V on vs off:
    0 PASS -> worse, 0 false RED in normal traffic. (Better is reported; none = not triggered, not a failure.)"""
    runs = [r for r in json.load(open(path, encoding="utf-8")) if r.get("seed", 0) >= 10]
    if not runs:
        raise SystemExit("No noise recordings 10+: run  python run_scenarios.py --cond 10 --seeds 5 --seed-from 10")
    order = {"PASS": 2, "LATE": 1, "FAIL": 0}
    better = worse = fr = 0
    print("\n================ FRESH: Fix L + V on noise recordings 10-14 ================")
    for r in runs:
        set_fixes(False); v1, _ = replay(r)
        set_fixes(True);  v2, f2 = replay(r)
        fr += f2
        if v1 != v2:
            print(f"  {'+' if order[v2] > order[v1] else '!!'} {r['scenario']} n{r['seed']}: {v1} -> {v2}")
        better += order[v2] > order[v1]
        worse += order[v2] < order[v1]
    print(f"FRESH: {len(runs)} runs | better {better} | worse {worse} | false RED in normal traffic {fr}")
    print("FRESH VERDICT:", "PASS - Fix L + V stay ON" if not worse and not fr else
          "FAIL - set LOCATE_FROM_READBACK / EXCLUDE_BY_NUMBER = False")


def main():
    if sys.argv[1:2] == ["--fresh"]:
        part_fresh(sys.argv[2]); return
    if sys.argv[1:2] == ["--taxiway"]:
        part_t2(sys.argv[2]); return
    files = sys.argv[1:]
    if not files:
        raise SystemExit("Give the old result files (dev, dev2, step1).")
    t_ok = part_t(files)
    l1, l2 = part_l(files)
    s_ok = part_s()
    set_fixes(True)
    print("\nVERDICT")
    print("  Fix T (taxiway):", "PASS" if t_ok else "FAIL - stays OFF")
    print("  Fix L + V (runway located by readback; unidentified excluded by its number):", "PASS - stay ON" if l1 and l2 and s_ok else
          "FAIL - set LOCATE_FROM_READBACK / EXCLUDE_BY_NUMBER = False in sentinel_state.py")
    print("\nPaste the whole output.")


if __name__ == "__main__":
    main()
