"""
ONE scorer for every test (fixes problem #19: each day had its own scorer, and two of them had bugs).

It always judges the SYSTEM'S FINAL DECISION (what the controller would see), never the raw text.

Outcomes:
  OK    : the system did the right thing
          - confirmed the right runway + callsign, or
          - flagged a callsign that really is not on frequency (pilot said a wrong callsign)
  FLAG  : the system asked a human although the call was fine (annoying, but safe)
  WRONG : the system showed something as fine that was NOT what was said (dangerous)
"""
import math
from sentinel_parse import extract


def judge(text, airport, traffic, true_runway, true_callsign):
    r = extract(text, airport, set(traffic))
    should_flag = true_callsign not in traffic          # pilot used a callsign nobody has
    if r["status"] == "FLAGGED":
        outcome = "OK" if should_flag else "FLAG"
    elif should_flag:
        outcome = "WRONG"                                # a non-existent callsign got confirmed
    elif (r["runway"], r["callsign"]) == (true_runway, true_callsign):
        outcome = "OK"
    else:
        outcome = "WRONG"
    return outcome, r


def wilson(k, n, z=1.96):
    """95% range for a rate k/n. With small n the range is wide — that IS the honest answer."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def summarize(outcomes):
    n = len(outcomes)
    counts = {o: outcomes.count(o) for o in ("OK", "FLAG", "WRONG")}
    lo, hi = wilson(counts["WRONG"], n)
    return {"n": n, **counts,
            "ok_rate": counts["OK"] / n if n else 0.0,
            "ok_range": wilson(counts["OK"], n),
            "wrong_rate_upper_95": hi}


def fmt(s):
    lo, hi = s["ok_range"]
    return (f"n={s['n']:>3} | OK {s['OK']:>3} ({100*s['ok_rate']:.0f}%, likely {100*lo:.0f}-{100*hi:.0f}%) "
            f"| FLAG {s['FLAG']:>3} | WRONG {s['WRONG']:>2} (true rate could be up to {100*s['wrong_rate_upper_95']:.1f}%)")
