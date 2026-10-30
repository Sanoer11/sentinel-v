"""
Tests for the scorer itself (problem #19). Every case is a bug we already hit for real.
Run:  python -m pytest -q test_scoring.py
"""
from scoring import judge, wilson, summarize

DEL = {"AIC2817", "AIC2871", "IGO5134", "AKJ1123", "FOLLOWME3"}


def test_wind_270_is_not_runway_27():
    # Day 1 bug: "27" matched inside "270 degrees"
    o, r = judge("Air India 2817, wind 270 degrees, runway 28, cleared to land", "VIDP", {"AIC2817", "IGO5134"}, "28", "AIC2817")
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


def test_similar_callsign_swap_is_no_longer_silent():
    # Was WRONG (heard the OTHER real flight, shown green). Now amber, naming the look-alike to confirm.
    o, r = judge("Air India 2871, runway 28, cleared to land", "VIDP", DEL, "28", "AIC2817")
    assert o == "AMBER" and r["status"] == "PROBABLE"


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


# ---- callsign anchoring (airline word garbled, flight number heard) ----

def test_garbled_airline_exact_number_is_amber_not_green():
    # real transcript of Sanoer's voice + radio: IFLY heard as "Air France"
    o, r = judge("Air France 5134, runway 27, near to land.", "VIDP", DEL, "27", "IGO5134")
    assert o == "AMBER" and r["status"] == "PROBABLE"


def test_readback_callsign_at_end_is_found():
    o, _ = judge("Runway 10, cleared for takeoff, Reply 2241.", "VAPO", {"IGO2241", "AIC947"}, "10", "IGO2241")
    assert o == "AMBER"


def test_anchor_never_changes_a_digit():
    # 5124 is not on frequency; 5134 is. Must NOT become 5134.
    o, r = judge("Reply 5124, runway 27, cleared to land.", "VIDP", DEL, "27", "IGO5134")
    assert o == "FLAG" and r["callsign"] is None


def test_anchor_refuses_when_two_airlines_share_the_number():
    traffic = DEL | {"AKJ5134"}
    o, _ = judge("Air France 5134, runway 27, cleared to land.", "VIDP", traffic, "27", "IGO5134")
    assert o == "FLAG"


def test_numbers_after_wind_or_runway_are_never_callsigns():
    traffic = {"AIC270", "IGO5134"}
    o, r = judge("Reply, wind 270, runway 27.", "VIDP", traffic, "27", "AIC270")
    assert r["callsign"] is None and o == "FLAG"


def test_clearly_heard_wrong_airline_is_still_flagged():
    # a KNOWN airline word that disagrees must stay a flag (anchoring only runs when no airline word)
    o, _ = judge("Akasa Air 5134, runway 27, cleared to land.", "VIDP", DEL, "27", "IGO5134")
    assert o == "FLAG"


def test_number_in_the_middle_is_not_used():
    # callsign position rule: a flight number buried mid-sentence is not trusted
    o, r = judge("Cleared to land, Reply, 5134, runway 27, wind calm, check gear down.", "VIDP", DEL, "27", "IGO5134")
    assert r["callsign"] is None


# ---- similar callsigns on frequency (issue #1: a two/three slip landing on another real flight) ----

def test_twin_on_frequency_is_never_green():
    T = {"IGO5134", "IGO5124", "AIC2817"}
    o, r = judge("IFLY 5124, runway 27, cleared to land.", "VIDP", T, "27", "IGO5134")
    # shown as "IGO5124 - similar IGO5134 on frequency, confirm": the right flight is on screen
    assert r["status"] == "PROBABLE" and "IGO5134" in r["amber"][0] and o == "AMBER"


def test_transposed_twin_is_flagged_amber():
    o, r = judge("Air India 2817, runway 28, cleared to land.", "VIDP", {"AIC2817", "AIC2871"}, "28", "AIC2817")
    assert o == "AMBER"


def test_different_airline_same_digits_is_not_a_twin():
    o, _ = judge("IFLY 5134, runway 27, cleared to land.", "VIDP", {"IGO5134", "AIC5124"}, "27", "IGO5134")
    assert o == "OK"


def test_no_twin_stays_green():
    o, _ = judge("IFLY 5134, runway 27, cleared to land.", "VIDP", {"IGO5134", "IGO7781"}, "27", "IGO5134")
    assert o == "OK"


# ---- one-digit runway (a lost digit must never become a real runway) ----

def test_one_digit_runway_is_flagged_not_padded():
    # "two niner" with the "two" lost -> "runway 9". Delhi HAS runway 09, so padding would be silent WRONG.
    for t in ["IFLY 5134, runway 9, cleared to land.", "IFLY 5134, runway niner, cleared to land."]:
        o, r = judge(t, "VIDP", DEL, "29R", "IGO5134")
        assert o == "FLAG" and r["runway"] is None, t


def test_two_digit_09_still_works():
    o, _ = judge("IFLY 5134, runway 09, cleared to land.", "VIDP", {"IGO5134"}, "09", "IGO5134")
    assert o == "OK"
