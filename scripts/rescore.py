"""
Re-score a saved results file with the CURRENT parser. No API calls, costs nothing.

  python scripts/rescore.py results/human_day3_20261029_150327.json

Shows, per clip, the old outcome and the new one, so every change is visible.
Remember: re-scoring the same data you fixed the code on is NOT proof. It only shows the fix
does what it was meant to do. Proof = a run on lines the fix never saw.
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
from scoring import judge_full, summarize, fmt

res = json.load(open(sys.argv[1], encoding="utf-8"))
ts_name = res["testset"]
ts = json.load(open(f"testsets/{ts_name}.json", encoding="utf-8"))
items = {it["id"]: it for it in ts["items"]}

new_all, changed = [], 0
for r in res["results"]:
    it = items[r["id"]]
    o, p = judge_full(it, r["heard"], second_text=r.get("heard2"))
    new_all.append((r["cond"], o))
    flag = "" if o == r["outcome"] else f"   <-- was {r['outcome']}"
    changed += o != r["outcome"]
    note = p["problems"] or p["amber"]
    print(f"{r['id']} {r['cond']:<20} {o:<5} {r['heard']}  {note}{flag}")

print(f"\n{changed} clip(s) changed outcome.\n")
for c in dict.fromkeys(c for c, _ in new_all):
    print(f"{c:<22} {fmt(summarize([o for cc, o in new_all if cc == c]))}")