"""
Experiment A14 (7 Nov 2026) - two fixes, judged ONLY on transcripts already saved (no new API calls).

Fix T (sentinel_parse.TARA_ALIAS): "Tara" followed by a number is read as "Vistara".
Fix U (sentinel_state.MAYBE_RUNWAY): a take-off/landing whose runway was heard glued ("runway 290, right") and never
       located goes into the picture as a "maybe" runway (29R); conflicts with it are AMBER "POSSIBLE RUNWAY CONFLICT".

RULES - written before any result:
  Fix T passes only if ALL hold:
    T1 wrong readbacks missed (shown MATCH) stays 0
    T2 correct readbacks shown RED does not rise
    T3 no scenario run gets a worse verdict, no new false RED
    T4 at least 5 calls from at least 2 voices lose a flag (status PROBABLE/FLAGGED -> CONFIRMED, or one AMBER fewer),
       and no call gains an alert
  Fix U passes only if ALL hold:
    U1 of the DEL_2023 runs that MISSED, at least 4 now raise RUNWAY_CONFLICT_POSSIBLE by the crossing call (step 2 or 3)
    U2 normal traffic (NORMAL_DEL): no new RED; at most 2 runs gain any RUNWAY_CONFLICT_POSSIBLE
    U3 no scenario run gets a worse verdict
    U4 T1 and T2 hold with U on
  A fix that fails stays OFF. Both are then checked together (all rules again).

Data: every saved scenario run (latest copy of each scenario/condition/noise recording) + the dev, dev2 and step1
readback sets. Run: python exp_a14.py

RESULTS (7 Nov, first run):
  Fix T FAIL: 17 calls lost a flag (2 voices), but 2 calls GAINED a RED - "Tara 9026" read as Vistara 9026 became a
              CALLSIGN MISMATCH for VTI926 (a correct readback). Stays OFF. The rules are not changed.
  Fix U FAIL: 5 of 6 missed DEL runs warned, but 2 runs got worse (RED -> AMBER). Cause: a bug, not the idea - the maybe
              entry, renamed by the readback, released the runway the readback had just located. Fixed (maybe entries are
              dropped once the readback locates the runway) and re-run below under the SAME rules.
RESULTS (7 Nov, second run, same rules):
  Fix U PASS: U1 4 of the 6 missed DEL runs now get AMBER "POSSIBLE RUNWAY CONFLICT" at the crossing call (the other 2:
              no glued digits to go on); the 6 LATE runs also get it on time, so 10 of 20 noisy DEL runs gain an AMBER at
              the crossing. U2 normal traffic: 0 new RED, 0 runs with a possible conflict. U3 0 runs worse. U4 0/75 wrong
              readbacks missed, 15 correct shown RED (unchanged). Verdicts are unchanged (RED expected, so still MISSED/LATE).
  Together (U on, T off): PASS. MAYBE_RUNWAY = True; TARA_ALIAS stays False.
"""
import json, glob, sys
from collections import Counter, defaultdict
import sentinel_parse, sentinel_state
from scoring import phases_of
from scenarios import SCENARIOS
import exp_a12

READBACK = ["results/dev_20261031_000600.json", "results/dev2_20261031_004232.json", "results/step1_20261031_013014.json"]


def runs():
    seen = {}
    for f in sorted(glob.glob("results/scenarios_2026*.json")):
        if "dry" in f or "locked" in f:
            continue
        for r in json.load(open(f, encoding="utf-8")):
            if r["cond"] == "text":
                continue
            seen[(r["scenario"], r["cond"], r.get("seed", 0))] = r
    return list(seen.values())


def play(run):
    sc = SCENARIOS[run["scenario"]]
    eng = sentinel_state.RunwayEngine(sc["airport"], sc["traffic"], sc["phases"])
    steps = []
    for s, (_, _, spk, _) in zip(run["steps"], sc["steps"]):
        rec = eng.call(s["t"], s["channel"], s["heard"], s["heard2"], hinted=s.get("hinted", False))
        steps.append({"spk": spk, "status": rec["analysis"]["status"], "alerts": [(a["level"], a["kind"]) for a in rec["alerts"]]})
    verdict, false_red = exp_a12.replay(run)
    return verdict, false_red, steps


def setfix(t, u):
    sentinel_parse.TARA_ALIAS, sentinel_state.MAYBE_RUNWAY = t, u


RANK = {"PASS": 0, "LATE": 1, "FAIL": 2}


def compare(t, u, R):
    setfix(False, False); base = {k: play(r) for k, r in R.items()}
    rb0 = exp_a12.readback_tally(READBACK)
    setfix(t, u); new = {k: play(r) for k, r in R.items()}
    rb1 = exp_a12.readback_tally(READBACK)
    setfix(False, False)
    worse = [k for k in R if RANK[new[k][0]] > RANK[base[k][0]] or (new[k][1] and not base[k][1])]
    better = [k for k in R if RANK[new[k][0]] < RANK[base[k][0]]]
    lost, gained, voices = 0, 0, set()
    for k in R:
        for s0, s1 in zip(base[k][2], new[k][2]):
            a0 = Counter(s0["alerts"]); a1 = Counter(s1["alerts"])
            if (s0["status"] in ("PROBABLE", "FLAGGED") and s1["status"] == "CONFIRMED") or sum((a0 - a1).values()):
                lost += 1; voices.add(s0["spk"])
            if sum((a1 - a0).values()):
                gained += 1
    missed_del = [k for k in R if k[0] == "DEL_2023" and base[k][0] == "FAIL"]
    warned = [k for k in missed_del if any(x[1] == "RUNWAY_CONFLICT_POSSIBLE" for st in new[k][2][2:4] for x in st["alerts"])]
    normal = [k for k in R if k[0] == "NORMAL_DEL"]
    norm_newred = [k for k in normal if sum(x[0] == "RED" for st in new[k][2] for x in st["alerts"]) > sum(x[0] == "RED" for st in base[k][2] for x in st["alerts"])]
    norm_possible = [k for k in normal if any(x[1] == "RUNWAY_CONFLICT_POSSIBLE" for st in new[k][2] for x in st["alerts"])]
    print(f"  scenario runs: {len(R)} | worse {len(worse)} {worse[:6]} | better {len(better)} {better[:6]}")
    print(f"  calls losing a flag: {lost} (voices {sorted(voices)}) | calls gaining an alert: {gained}")
    print(f"  readback: wrong missed {rb0[('WRONG','MATCH')]} -> {rb1[('WRONG','MATCH')]} | correct shown RED {rb0[('correct','MISMATCH')]} -> {rb1[('correct','MISMATCH')]}"
          f" | correct flagged AMBER {rb0[('correct','INCOMPLETE')]} -> {rb1[('correct','INCOMPLETE')]}")
    print(f"  DEL_2023 missed runs {len(missed_del)}, now warned (POSSIBLE by the crossing): {len(warned)} {warned}")
    print(f"  NORMAL_DEL runs {len(normal)}: new RED {len(norm_newred)} | with POSSIBLE conflict {len(norm_possible)} {norm_possible}")
    rb_ok = rb1[("WRONG", "MATCH")] == 0 and rb1[("correct", "MISMATCH")] <= rb0[("correct", "MISMATCH")]
    return dict(worse=worse, lost=lost, voices=voices, gained=gained, warned=warned, norm_newred=norm_newred,
                norm_possible=norm_possible, rb_ok=rb_ok)


def main():
    R = {(r["scenario"], r["cond"], r.get("seed", 0)): r for r in runs()}
    print("================ Fix T alone ================")
    t = compare(True, False, R)
    T = t["rb_ok"] and not t["worse"] and t["lost"] >= 5 and len(t["voices"]) >= 2 and t["gained"] == 0
    print("Fix T:", "PASS" if T else "FAIL")
    print("================ Fix U alone ================")
    u = compare(False, True, R)
    U = len(u["warned"]) >= 4 and not u["norm_newred"] and len(u["norm_possible"]) <= 2 and not u["worse"] and u["rb_ok"]
    print("Fix U:", "PASS" if U else "FAIL")
    if T or U:
        print("================ passing fixes together ================")
        b = compare(T, U, R)
        ok = b["rb_ok"] and not b["worse"] and not b["norm_newred"]
        print("Together:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
