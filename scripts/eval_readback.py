"""
Step 2 check, no API calls: pair every tower call with its pilot readback (same noise level)
from saved transcripts, run the readback check, and compare with the truth.

  python scripts/eval_readback.py results/dev_20261031_000600.json results/dev2_20261031_004232.json results/step1_20261031_013014.json

Wrong readback (pilot really said something else):  RED = caught | AMBER = asked to confirm | MATCH = MISSED (dangerous)
Correct readback:                                    MATCH = good  | AMBER = asked to confirm | RED = false alarm
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
from collections import Counter
from sentinel_state import RunwayEngine
from scoring import phases_of, wilson


def main(files):
    tally, worst = Counter(), []
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
            e = RunwayEngine(it["airport"], it["traffic"], ph)
            e.call(0, "tower", tw["heard"], tw.get("heard2"))
            r = e.call(4, "pilot", rb["heard"], rb.get("heard2"))
            p = e.pending[-1] if e.pending else None
            verdict = p.get("verdict") if p else "NO_CLEARANCE"
            if verdict is None:
                verdict = "UNMATCHED"
            wrong_rb = it["truth"]["callsign"] not in it["traffic"] or any(t.startswith("wrong_readback") for t in it["traps"])
            key = ("WRONG readback" if wrong_rb else "correct readback", verdict)
            tally[key] += 1
            if wrong_rb and verdict == "MATCH" or (not wrong_rb and verdict == "MISMATCH"):
                worst.append((res["testset"], iid, cond, verdict, tw["heard"], rb["heard"], p.get("why") if p else None))
    for k in sorted(tally):
        print(f"  {k[0]:<17} {k[1]:<13} {tally[k]}")
    n_wrong = sum(v for k, v in tally.items() if k[0] == "WRONG readback")
    missed = tally[("WRONG readback", "MATCH")]
    lo, hi = wilson(missed, n_wrong)
    print(f"\nWrong readbacks missed: {missed}/{n_wrong} (true rate could be up to {100*hi:.1f}%)")
    print("\nEvery missed wrong readback and every false RED, so nothing is hidden:")
    for w in worst:
        print(f"  {w[0]} {w[1]} {w[2]} {w[3]}\n     tower: {w[4]}\n     pilot: {w[5]}\n     why  : {w[6]}")


if __name__ == "__main__":
    main(sys.argv[1:])
