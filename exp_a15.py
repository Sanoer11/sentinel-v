"""
Experiment A15 (7 Nov 2026, after the locked exam) - Fix S (sentinel_parse.SUFFIX_CALLSIGN): a 5-6 digit number at the
start or end of a call whose LAST digits are exactly one flight on frequency is read as that flight ("36053" -> IGO6053),
always AMBER "confirm callsign".

Judged ONLY on practice data saved BEFORE the locked exam (every saved scenario run except the locked one, and the dev,
dev2 and step1 readback sets). The locked exam's transcripts are NOT used: its numbers stay as they are, for freeze-v3.

RULES - written before any result. Fix S passes only if ALL hold:
  S1 wrong readbacks missed (shown MATCH) stays 0
  S2 correct readbacks shown RED does not rise
  S3 no scenario run gets a worse verdict, no new false RED
  S4 at least 10 calls from at least 2 voices lose a flag (FLAGGED -> PROBABLE, or one AMBER fewer)
     and correct readbacks shown MATCH do not fall
Run: python exp_a15.py

RESULT (7 Nov): PASS. 20 calls lost a flag (voices p1, p2, tower), 0 gained an alert, 0 runs worse; correct readbacks
shown MATCH 179 -> 181, asked to confirm 88 -> 86; wrong readbacks missed 0; correct shown RED 15 -> 15.
SUFFIX_CALLSIGN = True (after freeze-v3: the locked exam numbers do not include it).
"""
import sentinel_parse, sentinel_state
import exp_a14 as base


def setfix(s, u=True):
    sentinel_parse.SUFFIX_CALLSIGN = s
    sentinel_parse.TARA_ALIAS = False
    sentinel_state.MAYBE_RUNWAY = True          # A14 is on in freeze-v3: compare against that


def compare(R):
    from collections import Counter
    import exp_a12
    setfix(False); b = {k: base.play(r) for k, r in R.items()}; rb0 = exp_a12.readback_tally(base.READBACK)
    setfix(True);  n = {k: base.play(r) for k, r in R.items()}; rb1 = exp_a12.readback_tally(base.READBACK)
    setfix(False)
    worse = [k for k in R if base.RANK[n[k][0]] > base.RANK[b[k][0]] or (n[k][1] and not b[k][1])]
    better = [k for k in R if base.RANK[n[k][0]] < base.RANK[b[k][0]]]
    lost, gained, voices = 0, 0, set()
    for k in R:
        for s0, s1 in zip(b[k][2], n[k][2]):
            a0, a1 = Counter(s0["alerts"]), Counter(s1["alerts"])
            if (s0["status"] == "FLAGGED" and s1["status"] in ("PROBABLE", "CONFIRMED")) or sum((a0 - a1).values()):
                lost += 1; voices.add(s0["spk"])
            if sum((a1 - a0).values()):
                gained += 1
    print(f"  scenario runs {len(R)} | worse {len(worse)} {worse[:6]} | better {len(better)} {better[:6]}")
    print(f"  calls losing a flag {lost} (voices {sorted(voices)}) | calls gaining an alert {gained}")
    for key in [("WRONG", "MATCH"), ("correct", "MISMATCH"), ("correct", "MATCH"), ("correct", "INCOMPLETE"), ("correct", "NO_CLEARANCE")]:
        print(f"  readback {key}: {rb0[key]} -> {rb1[key]}")
    ok = (rb1[("WRONG", "MATCH")] == 0 and rb1[("correct", "MISMATCH")] <= rb0[("correct", "MISMATCH")] and not worse
          and lost >= 10 and len(voices) >= 2 and rb1[("correct", "MATCH")] >= rb0[("correct", "MATCH")])
    print("Fix S:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    R = {(r["scenario"], r["cond"], r.get("seed", 0)): r for r in base.runs()}
    compare(R)
