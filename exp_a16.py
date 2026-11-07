"""
Experiment A16 (7 Nov 2026) - Fix R (sentinel_parse.ARRIVE_AS_RIGHT): "<runway number>, arrive/arrived/arrives" is read
as "<number> right" ("runway 29, arrived" -> 29R).

Written BEFORE the data it is judged on: a new PRACTICE run with the exam's Timbre v2.5 voices (now used up, so allowed
for development) at 10 dB with NEW noise recordings 200-209 (`python run_scenarios.py --v25`), plus every practice run
saved before. The locked exam's own transcripts (noise 100-104) are NOT used.

RULES - Fix R passes only if ALL hold, on all practice data together:
  R1 wrong readbacks missed (shown MATCH) stays 0
  R2 correct readbacks shown RED does not rise
  R3 no scenario run gets a worse verdict, no new false RED
  R4 at least 8 calls from at least 2 voices lose a flag (FLAGGED -> PROBABLE/CONFIRMED, or one AMBER fewer)
Also reported (not a rule): how the v25 practice runs score with A14 + A15, before and after Fix R.
Run: python exp_a16.py

RESULT (7 Nov 2026, v25 practice file results/scenarios_v25_20261107_125432.json + all earlier practice runs, 248 runs):
  FAIL on R4. worse runs 0, new false RED 0, wrong readbacks missed 0 -> 0, correct shown RED 15 -> 15,
  but only 3 calls lost a flag, all from one voice (needs 8 from 2+). The new voices rarely said "arrived".
  ARRIVE_AS_RIGHT stays False. v25 practice runs (A14 + A15 on): PASS 62/80, LATE 1, FAIL 17 - same with Fix R.
  Loader fix before judging (no rule change): base.runs() only read scenarios_2026*.json, so v25 files were added.
"""
import glob, json
from collections import Counter
import sentinel_parse, sentinel_state
import exp_a14 as base
import exp_a12


def setfix(r):
    sentinel_parse.ARRIVE_AS_RIGHT = r
    sentinel_parse.TARA_ALIAS = False
    sentinel_parse.SUFFIX_CALLSIGN = True
    sentinel_state.MAYBE_RUNWAY = True


def v25_runs():
    out = []
    for f in sorted(glob.glob("results/scenarios_v25_*.json")):
        out += [r for r in json.load(open(f, encoding="utf-8")) if r["cond"] != "text"]
    return out


def main():
    R = {(r["scenario"], r["cond"], r.get("seed", 0)): r for r in base.runs() + v25_runs()}
    v25 = [k for k in R if 200 <= k[2] <= 209]
    print(f"practice runs {len(R)} (v25 voices, noise 200-209: {len(v25)})")
    if not v25:
        raise SystemExit("No v25 practice runs yet: run  python run_scenarios.py --v25  first.")
    setfix(False); b = {k: base.play(r) for k, r in R.items()}; rb0 = exp_a12.readback_tally(base.READBACK)
    setfix(True);  n = {k: base.play(r) for k, r in R.items()}; rb1 = exp_a12.readback_tally(base.READBACK)
    setfix(False)
    worse = [k for k in R if base.RANK[n[k][0]] > base.RANK[b[k][0]] or (n[k][1] and not b[k][1])]
    lost, gained, voices = 0, 0, set()
    for k in R:
        for s0, s1 in zip(b[k][2], n[k][2]):
            a0, a1 = Counter(s0["alerts"]), Counter(s1["alerts"])
            if (s0["status"] == "FLAGGED" and s1["status"] in ("PROBABLE", "CONFIRMED")) or sum((a0 - a1).values()):
                lost += 1; voices.add(s0["spk"])
            if sum((a1 - a0).values()):
                gained += 1
    print(f"  worse {len(worse)} {worse[:6]} | calls losing a flag {lost} (voices {sorted(voices)}) | gaining an alert {gained}")
    for key in [("WRONG", "MATCH"), ("correct", "MISMATCH"), ("correct", "MATCH"), ("correct", "INCOMPLETE")]:
        print(f"  readback {key}: {rb0[key]} -> {rb1[key]}")
    for label, res in (("before Fix R", b), ("after Fix R", n)):
        c = Counter(res[k][0] for k in v25)
        print(f"  v25 practice runs {label}: {dict(c)}  (PASS = on time)")
    ok = rb1[("WRONG", "MATCH")] == 0 and rb1[("correct", "MISMATCH")] <= rb0[("correct", "MISMATCH")] and not worse \
        and lost >= 8 and len(voices) >= 2
    print("Fix R:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
