"""
Tests for the scorer itself (problem #19). Every case is a bug we already hit for real.
Run:  python -m pytest -q test_scoring.py
"""
from scoring import judge, wilson, summarize

DEL = {"AIC2817", "AIC2871", "IGO5134", "AKJ1123", "FOLLOWME3"}


def test_wind_270_is_not_runway_27():
    # Day 1 bug: "27" matched inside "270 degrees"
    o, r = judge("Air India 2817, wind 270 degrees, runway 28, cleared to land", "VIDP", DEL, "28", "AIC2817")
    assert o == "OK" and r["runway"] == "28"


def test_pilot_wrong_callsign_is_never_hidden():
    # Day 3b bug: parser auto-corrected the pilot's real "5124" into 5134 and showed it as fine
    o, r = judge("Cleared to land, runway 27. IFLY 5124.", "VIDP", DEL, "27", "IGO5124")
    assert o == "OK" and r["status"] == "FLAGGED"


def test_prisma_digit_slip_is_flag_not_wrong():
    # Prisma mishears 5134 as 5124: system must ask a human, not guess
    o, _ = judge("I fly 5124, runway 27, cleared to land.", "VIDP", DEL, "27", "IGO5134")
    assert o == "FLAG"


def test_vehicle_without_number_is_not_confirmed():
    # Day 3 bug: "Follow Me please" was confirmed as some Follow Me
    o, _ = judge("Tower, follow me please. Runway 29 right cross", "VIDP", DEL, "29R", "FOLLOWME3")
    assert o == "FLAG"


def test_similar_callsign_swap_is_caught_as_wrong():
    # The dangerous case: heard the OTHER real flight. Scorer must call it WRONG.
    o, _ = judge("Air India 2871, runway 28, cleared to land", "VIDP", DEL, "28", "AIC2817")
    assert o == "WRONG"


def test_valid_but_wrong_runway_is_wrong():
    o, _ = judge("IFLY 5134, runway 28, cleared to land", "VIDP", DEL, "27", "IGO5134")
    assert o == "WRONG"


def test_impossible_runway_is_flag():
    o, _ = judge("Air India 2817, runway 37, cleared to land", "VIDP", DEL, "27", "AIC2817")
    assert o == "FLAG"


def test_niner_and_side_formats():
    for t in ["IFLY 5134, cross runway 29er, right at Bravo",
              "Crossing runway 29 right, IFL Y 5134",
              "IFLY 5134 cross runway 2, 9R"]:
        o, _ = judge(t, "VIDP", DEL, "29R", "IGO5134")
        assert o == "OK", t


def test_wilson_range_is_honest():
    lo, hi = wilson(0, 19)
    assert lo == 0 and 0.15 < hi < 0.2       # 0 wrong out of 19 still allows up to ~17%
    lo, hi = wilson(0, 600)
    assert hi < 0.01                          # 0 out of 600 -> under 1%


def test_summary_counts():
    s = summarize(["OK", "OK", "FLAG", "WRONG"])
    assert (s["OK"], s["FLAG"], s["WRONG"], s["n"]) == (2, 1, 1, 4)
