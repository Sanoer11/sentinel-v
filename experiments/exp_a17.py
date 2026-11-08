"""
Experiment A17 (7 Nov 2026) - five fixes, each traced to an exact miss in the v25 practice run (exam voices, noise
200-209) and counted on ALL saved practice transcripts before any code was written.

  G  sentinel_parse.GLUE_RUNWAY_SIDE  "runway 290, right" -> 29R. A runway number glued after "niner" (290, 298, 2900)
     with the SIDE heard: 48 of 48 had the right side and the right first two digits (61 of 61 for the digits).
     Only "X9 + 1-2 extra digits + side", only if X9+side exists here. Always AMBER ("runway heard as 290R").
  N  sentinel_parse.NINER0_CALLSIGN   "Tara 9026" -> VTI926. "niner" written 90 inside a flight number: 10 of 10.
     Only if undoing the niner glue gives exactly ONE flight on frequency and the raw number is none. Always AMBER.
  K  sentinel_state.TAKEOFF_THEN_CROSS  An unidentified CROSS of a runway that has a take-off clearance cannot be the
     same aircraft cleared twice (it cannot cross the runway it is departing from) -> the conflict stays RED.
  X  sentinel_state.CALLSIGN_ONLY_UNCLEAR  Tower callsign lost, instruction + runway heard: "hold short" read back as
     "crossing" stays RED (the unclear part has nothing to do with the instruction), and "if it does what it read
     back" is checked under the readback's callsign.
  P  sentinel_actions CLEAR_TAKEOFF  "clear for takeoff" / "cleared to take off" = TAKEOFF (3 times, v25 tower;
     said "cleared for takeoff" every time). Without it the take-off never enters the runway picture.

Not fixed on purpose: a pilot callsign with a misheard digit that is on NO flight ("Akasa Air 113", "Air India 3817")
stays RED. The deliberately wrong callsigns in the test sets are exactly that (off-frequency look-alikes), and in real
traffic an aircraft missing from our list looks the same. Making them AMBER would hide real errors.

RULES (written before the code) - each fix alone on top of the current engine, then all five together, on every
practice scenario run (168 before the exam + 80 v25) and the saved readback transcripts. A fix passes only if:
  R1 wrong readbacks missed (readback tally WRONG -> MATCH) stays 0, and no deliberately wrong scenario readback
     goes silent
  R2 correct readbacks shown RED (correct -> MISMATCH) does not rise
  R3 no scenario run gets a worse verdict, and no new false RED in normal traffic
  R4 at least 1 run gets a better verdict, or at least 5 calls lose a flag
Fixes that fail stay off. The held-out check is NEW audio nobody has seen (own-voice recordings), not this data.
Run: python experiments/exp_a17.py

RESULT (7 Nov 2026, 248 practice runs: 168 before the exam + 80 v25):
  G PASS (13 runs better, 28 calls lose a flag)   N PASS (1 better)   K PASS (2 better)   P PASS (1 better)
  X FAIL - correct readbacks shown RED 15 -> 17: when the tower's callsign is lost, Prisma often garbled the
    instruction too ("cleared to land" heard as "cleared for takeoff", "via Bravo" as "cross"). Kept off.
  G+N+K+P together: 18 runs better, 0 worse, 0 silent, wrong readbacks missed 0 -> 0, correct shown RED 15 -> 15.
    practice 10 dB on time 137 -> 147 of 160, false RED in normal traffic 2 -> 2
    v25 (exam voices, new noise) on time 62 -> 70 of 80 (Delhi 2023 4 -> 9 of 10, Mumbai 9 -> 10, hold-as-cross 4 -> 6)
  These fixes were designed on this data, so these numbers are NOT a held-out result.
  After the first judgement the old tests (real A2/A3 transcripts) caught two over-reaches; both were narrowed to the
  evidence and everything re-judged under the SAME rules (same numbers): N only 4 digits with one "0" after a "9"
  ("98714" can be real digits); G steps back when the second listen names another runway or callsign.
  Line check (scoring.judge on 864 saved practice lines, dev/dev2/step1/human_day3): shown fine but wrong 0 -> 0,
  FLAG 210 -> 208, AMBER 292 -> 294.
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import glob, json
from collections import Counter
import sentinel_parse, sentinel_state, sentinel_actions
import exp_a14 as base
import exp_a12

FLAGS = {"G": (sentinel_parse, "GLUE_RUNWAY_SIDE"), "N": (sentinel_parse, "NINER0_CALLSIGN"),
         "K": (sentinel_state, "TAKEOFF_THEN_CROSS"), "X": (sentinel_state, "CALLSIGN_ONLY_UNCLEAR"),
         "P": (sentinel_actions, "CLEAR_TAKEOFF")}
WRONG_STEPS = {"HOLD_AS_CROSS": 3, "TWIN_CALLSIGN": 1}


def setfix(on):
    for k, (mod, name) in FLAGS.items():
        setattr(mod, name, k in on)


def all_runs():
    R = {(r["scenario"], r["cond"], r.get("seed", 0)): r for r in base.runs()}
    for f in sorted(glob.glob("results/scenarios_v25_*.json")):
        for r in json.load(open(f, encoding="utf-8")):
            if r["cond"] != "text":
                R[(r["scenario"], r["cond"], r.get("seed", 0))] = r
    return R


def judge(R, on, label):
    setfix(set()); b = {k: base.play(r) for k, r in R.items()}; rb0 = exp_a12.readback_tally(base.READBACK)
    setfix(on);    n = {k: base.play(r) for k, r in R.items()}; rb1 = exp_a12.readback_tally(base.READBACK)
    setfix(set())
    worse = [k for k in R if base.RANK[n[k][0]] > base.RANK[b[k][0]] or (n[k][1] and not b[k][1])]
    better = [k for k in R if base.RANK[n[k][0]] < base.RANK[b[k][0]]]
    silent = [k for k in R if k[0] in WRONG_STEPS and not n[k][2][WRONG_STEPS[k[0]]]["alerts"]]
    lost = 0
    for k in R:
        for s0, s1 in zip(b[k][2], n[k][2]):
            a0, a1 = Counter(x for x in s0["alerts"] if x[0] == "AMBER"), Counter(x for x in s1["alerts"] if x[0] == "AMBER")
            if (s0["status"] == "FLAGGED" and s1["status"] != "FLAGGED") or sum((a0 - a1).values()):
                lost += 1
    ok = rb1[("WRONG", "MATCH")] == 0 and not silent and rb1[("correct", "MISMATCH")] <= rb0[("correct", "MISMATCH")] \
        and not worse and (better or lost >= 5)
    v25 = [k for k in R if 200 <= k[2] <= 209]
    print(f"{label:<6} better {len(better):>3} worse {len(worse)} {worse[:4]} silent {len(silent)} | calls losing a flag {lost:>3}"
          f" | wrong missed {rb0[('WRONG', 'MATCH')]}->{rb1[('WRONG', 'MATCH')]}"
          f" correct RED {rb0[('correct', 'MISMATCH')]}->{rb1[('correct', 'MISMATCH')]}"
          f" | v25 {dict(Counter(b[k][0] for k in v25))} -> {dict(Counter(n[k][0] for k in v25))}"
          f" | {'PASS' if ok else 'FAIL'}")
    return ok, b, n


def main():
    R = all_runs()
    print(f"practice runs {len(R)}")
    passed = [k for k in FLAGS if judge(R, {k}, k)[0]]
    ok, b, n = judge(R, set(passed), "+".join(passed) or "none")
    prac = [k for k in R if k[1] == "10" and k[2] < 100]
    v25 = [k for k in R if 200 <= k[2] <= 209]
    for name, ks in (("practice 10 dB", prac), ("v25", v25)):
        on_time = lambda res: sum(res[k][0] == "PASS" for k in ks)
        fr = lambda res: sum(res[k][1] for k in ks if k[0] == "NORMAL_DEL")
        print(f"  {name}: on time {on_time(b)} -> {on_time(n)} of {len(ks)} | false RED normal {fr(b)} -> {fr(n)}")
    for sc in sorted({k[0] for k in v25}):
        ks = [k for k in v25 if k[0] == sc]
        print(f"    v25 {sc:<14} {dict(Counter(b[k][0] for k in ks))} -> {dict(Counter(n[k][0] for k in ks))}")
    print("ON:", passed)


if __name__ == "__main__":
    main()
