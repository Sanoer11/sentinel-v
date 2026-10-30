"""
Experiment A3 — test candidate Fix N ("niner" glued inside a flight number) on audio we ALREADY have.

Dev run 31 Oct: "IFLY niner seven one four" -> "90714" / "98714", "eight niner niner fife" -> "89995".
Same glue as runway "290". Fix N: ask the same audio again in verbatim, accept its callsign only if
it is the glued number with a 0/9/8 removed right after a 9, the flight is on frequency, and the
runway agrees in both listens. Always AMBER.

RULE FIXED NOW (before seeing results):
  Fix N goes live only if it rescues 3+ DIFFERENT dev lines AND produces 0 WRONG.
  If it fails, NINER_GLUE_FIX stays False and these stay flags.

No new TTS: re-uses the cached dev audio in audio_eval/dev/. Only the clips that need it get a call.
Run:   python exp_a3.py results/dev_20261031_000600.json
Cost:  one verbatim STT call per qualifying clip (expected ~15-20)  ~ Rs 1
"""
import os
import sys
import json
import datetime

from gnani_client import stt
from sentinel_parse import extract, needs_callsign_second_listen, callsign_second_listen
from scoring import judge
import scoring


def audio_path(iid, cond):
    clean = f"audio_eval/dev/{iid}.wav"
    return clean if cond == "clean" else clean.replace(".wav", f"_snr{cond.replace('dB', '')}.wav")


def main():
    res = json.load(open(sys.argv[1], encoding="utf-8"))
    ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
    items = {it["id"]: it for it in ts["items"]}
    todo = []
    for r in res["results"]:
        it = items[r["id"]]
        if needs_callsign_second_listen(extract(r["heard"], it["airport"], set(it["traffic"]))):
            todo.append((r, it))
    print(f"{len(todo)} clips qualify (5+ digit number, only a callsign problem, runway fine)\n")
    rows, rescued, wrong = [], set(), 0
    for r, it in todo:
        p = audio_path(r["id"], r["cond"])
        if not os.path.exists(p):
            print(f"  missing audio {p} - skipped"); continue
        t2 = stt(p, it["channel"], fmt="verbatim")
        args = (it["airport"], set(it["traffic"]), it["truth"]["runway"], it["truth"]["callsign"])
        before, _ = judge(r["heard"], *args)
        r1 = extract(r["heard"], it["airport"], set(it["traffic"]))
        r3 = callsign_second_listen(r1, t2, it["airport"], set(it["traffic"]), force=True)
        after = scoring.outcome_of(r3, *args[1:])
        wrong += after == "WRONG"
        if before == "FLAG" and after in ("OK", "AMBER"):
            rescued.add(r["id"])
        print(f"{r['id']} {r['cond']:5} truth {it['truth']['callsign']:<9} {before} -> {after}")
        print(f"     first : {r['heard']}\n     second: {t2}")
        rows.append({"id": r["id"], "cond": r["cond"], "heard": r["heard"], "heard2": t2, "before": before, "after": after})
    ok = len(rescued) >= 3 and wrong == 0
    print(f"\nRescued {len(rescued)} different lines {sorted(rescued)}, WRONG {wrong}.")
    print("RULE: 3+ lines and 0 WRONG ->", "PASS: Fix N can go live." if ok else "FAIL: Fix N stays off.")
    os.makedirs("results", exist_ok=True)
    out = f"results/exp_a3_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {out}. Paste the whole output.")


if __name__ == "__main__":
    main()
