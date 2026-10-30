"""
ONE scorer for every test (fixes problem #19: each day had its own scorer, and two of them had bugs).

It always judges the SYSTEM'S FINAL DECISION (what the controller would see), never the raw text.

Outcomes:
  OK    : the system did the right thing
          - confirmed the right runway + callsign, or
          - flagged a callsign that really is not on frequency (pilot said a wrong callsign)
  AMBER : right answer, shown amber ("probable") because one part was identified indirectly
  FLAG  : the system asked a human although the call was fine (annoying, but safe)
  WRONG : the system showed something as fine that was NOT what was said (dangerous)
"""
import math
from sentinel_parse import extract, second_listen, callsign_second_listen, vehicle_second_listen


def judge(text, airport, traffic, true_runway, true_callsign, second_text=None):
    r = extract(text, airport, set(traffic))
    if second_text is not None:
        r = second_listen(r, second_text, airport, set(traffic))
        r = callsign_second_listen(r, second_text, airport, set(traffic))
        r = vehicle_second_listen(r, second_text, airport, set(traffic))
    return outcome_of(r, traffic, true_runway, true_callsign), r


def outcome_of(r, traffic, true_runway, true_callsign):
    """Score a parser result (what the controller would see) against the truth."""
    should_flag = true_callsign not in traffic          # pilot used a callsign nobody has
    right = (r["runway"], r["callsign"]) == (true_runway, true_callsign)
    if r["status"] == "FLAGGED":
        return "OK" if should_flag else "FLAG"
    if (r["status"] == "PROBABLE" and not should_flag and r["runway"] == true_runway
            and any(true_callsign in a for a in r["amber"])):
        return "AMBER"                    # amber that names the true flight as the look-alike to confirm
    if should_flag or not right:
        return "WRONG"                    # shown as fine/probable, but not what was said
    if r["status"] == "PROBABLE":
        return "AMBER"                    # right, but a human is asked to glance at it
    return "OK"


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
    counts = {o: outcomes.count(o) for o in ("OK", "AMBER", "FLAG", "WRONG")}
    lo, hi = wilson(counts["WRONG"], n)
    return {"n": n, **counts,
            "ok_rate": counts["OK"] / n if n else 0.0,
            "ok_range": wilson(counts["OK"], n),
            "wrong_rate_upper_95": hi}


def fmt(s):
    lo, hi = s["ok_range"]
    return (f"n={s['n']:>3} | OK {s['OK']:>3} ({100*s['ok_rate']:.0f}%, likely {100*lo:.0f}-{100*hi:.0f}%) "
            f"| AMBER {s['AMBER']:>3} | FLAG {s['FLAG']:>3} | WRONG {s['WRONG']:>2} (true rate could be up to {100*s['wrong_rate_upper_95']:.1f}%)")


# ---------------------------------------------------------------------------
# Step 1: judge the WHOLE call - callsign, every runway, the instruction for each, call-level
# instructions (go around / stop) and the "behind traffic" condition.
# ---------------------------------------------------------------------------
_MAP = {"land": "LAND", "takeoff": "TAKEOFF", "lineup": "LINEUP", "cross": "CROSS", "hold": "HOLD_SHORT"}


def truth_of(it):
    """Truth for any test line. Old dev/dev2 lines get it from their template."""
    t = it["truth"]
    if "instructions" in t:
        return t["instructions"], t["call_actions"], t["conditional"]
    if it["action"] == "vehicle":
        rom = it["roman"].lower()
        act = "REQ_CROSS" if ("cross" in rom or "olandaycha" in rom) else "REQ_ENTER" if "fod" in rom else "REPORT_BIRDS"
    else:
        act = _MAP[it["action"]]
    return [[t["runway"], act]], [], False


def phases_of(it):
    """Aircraft air/ground state, as ADS-B would give it. Old lines: landing = airborne."""
    if "phase" in it:
        return it["phase"]
    if it["action"] in _MAP:
        return {it["truth"]["callsign"]: "air" if it["action"] == "land" else "ground"}
    return None


def judge_full(it, text, second_text=None):
    from sentinel_actions import analyse
    r = analyse(text, it["airport"], it["traffic"], it["channel"], phases_of(it), second_text)
    tins, tcalls, tcond = truth_of(it)
    tcs = it["truth"]["callsign"]
    should_flag = tcs not in it["traffic"]
    if r["status"] == "FLAGGED":
        return ("OK" if should_flag else "FLAG"), r
    if should_flag:
        return "WRONG", r
    shown = {x["runway"]: x["action"] for x in r["instructions"]}
    problems = []
    for rw, act in tins:
        if rw not in shown:
            problems.append(f"runway {rw} missing")
        elif shown[rw] is not None and shown[rw] != act:
            problems.append(f"{rw}: shown {shown[rw]}, said {act}")
    problems += [f"extra runway {rw} shown" for rw in shown if rw not in {a for a, _ in tins}]
    problems += [f"{c} missing" for c in tcalls if c not in r["call_actions"]]
    problems += [f"extra {c} shown" for c in r["call_actions"] if c not in tcalls]
    if tcond and not any("conditional" in a for a in r["amber"]):
        problems.append("condition 'behind traffic' lost")
    cs_ok = r["callsign"] == tcs or any(tcs in a for a in r["amber"])
    if problems or not cs_ok:
        r = dict(r, why_wrong=problems + ([] if cs_ok else [f"callsign shown {r['callsign']}, said {tcs}"]))
        return "WRONG", r
    return ("AMBER" if r["status"] == "PROBABLE" else "OK"), r