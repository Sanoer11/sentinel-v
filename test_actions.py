"""
Step 1 tests: instruction per runway. ICAO Doc 4444 phrases + real Prisma transcripts from dev/dev2.
Run:  python -m pytest -q test_actions.py
"""
from sentinel_actions import analyse

DEL = {"IGO5134", "AIC2817", "AKJ1123", "FOLLOWME5", "FOLLOWME3"}


def acts(r):
    return [(x["runway"], x["action"], x["strength"]) for x in r["instructions"]]


# ---- ICAO phrases ----

def test_two_runways_in_one_call():
    r = analyse("IFLY five one three four, cross runway two niner left, hold short runway two niner right.", "VIDP", DEL)
    assert acts(r) == [("29L", "CROSS", "strong"), ("29R", "HOLD_SHORT", "strong")] and r["status"] == "CONFIRMED"


def test_second_runway_must_exist_too():
    r = analyse("IFLY 5134, cross runway 29L, hold short runway 39R.", "VIDP", DEL)
    assert r["status"] == "FLAGGED" and any("39R does not exist" in p for p in r["problems"])


def test_taxi_to_holding_point_is_not_entering():
    r = analyse("Air India 2817, taxi to holding point runway 28 via Bravo.", "VIDP", DEL)
    assert acts(r) == [("28", "TAXI_HP", "strong")]


def test_conditional_clearance_is_amber():
    r = analyse("Akasa Air 1123, behind the landing A320, line up and wait runway 27, behind.", "VIDP", DEL)
    assert acts(r)[0][1] == "LINEUP" and r["status"] == "PROBABLE" and any("conditional" in a for a in r["amber"])


def test_go_around_and_stop_need_no_runway():
    assert analyse("IFLY 5134, go around, I say again, go around.", "VIDP", DEL)["call_actions"] == ["GO_AROUND"]
    assert analyse("Air India 2817, stop immediately, I say again, stop immediately.", "VIDP", DEL)["call_actions"] == ["STOP"]


def test_before_takeoff_is_not_takeoff():
    # dev d010a 0dB: "report vacated" heard as "before takeoff" (truth: CROSS)
    r = analyse("A flight, 3792, got runway 28 before takeoff.", "VIDP", {"IGO3792"})
    assert all(x["action"] != "TAKEOFF" for x in r["instructions"])


# ---- real transcripts: clipped start of the phrase -> weak cue -> amber ----

def test_clipped_hold_short_is_amber_hold_short():
    r = analyse("Taking short runway 10, Akasa Air 6648.", "VAPO", {"AKJ6648"})
    assert acts(r) == [("10", "HOLD_SHORT", "weak")] and r["status"] == "PROBABLE"


def test_clipped_line_up_and_to_land():
    assert acts(analyse("I love and wait runway 28, Akasa Air 4924.", "VAPO", {"AKJ4924"}))[0][1:] == ("LINEUP", "weak")
    assert acts(analyse("Request to land runway 09, I fly 5093.", "VABB", {"IGO5093"}))[0][1:] == ("LAND", "weak")


def test_crossing_short_is_a_conflict():
    # dev d002b: "Holding short" heard as "Crossing short" - the two opposite instructions
    r = analyse("Crossing short runway 32, Air India 9158.", "VABB", {"AIC9158"})
    assert r["status"] == "FLAGGED" and r["instructions"][0]["conflict"]


def test_no_instruction_is_amber_not_green():
    r = analyse("Taxiway runway 09, Air India 2031.", "VABB", {"AIC2031"})
    assert r["instructions"][0]["action"] is None and r["status"] == "PROBABLE"


# ---- aircraft state (ADS-B air/ground) ----

def test_takeoff_for_airborne_aircraft_is_flagged():
    # dev2 e012a 0dB: "cleared to land" heard as "cleared for takeoff" - text alone can't tell
    r = analyse("I fly 7981, runway 14, cleared for takeoff.", "VABB", {"IGO7981"}, phases={"IGO7981": "air"})
    assert r["status"] == "FLAGGED"
    assert analyse("I fly 7981, runway 14, cleared for takeoff.", "VABB", {"IGO7981"})["status"] == "CONFIRMED"


def test_land_for_aircraft_on_ground_is_flagged():
    r = analyse("Air India 2817, runway 28, cleared to land.", "VIDP", DEL, phases={"AIC2817": "ground"})
    assert r["status"] == "FLAGGED"


# ---- vehicle channel ----

def test_vehicle_cross_is_a_request_and_hold_is_its_position():
    r = analyse("Follow me, 5 runway 28 cross करना है, Bravo पे hold short जाना है।", "VIDP", DEL, channel="airside")
    assert acts(r) == [("28", "REQ_CROSS", "strong")] and r["status"] == "CONFIRMED"


def test_vehicle_fod_check_is_enter_request():
    r = analyse("Tower, Follow Me 3, runway 10 पे FOD check के लिए enter करना है, permission चाहिए।", "VIDP", DEL, channel="airside")
    assert acts(r)[0][1] == "REQ_ENTER"


def test_vehicle_birds_report():
    r = analyse("टॉवर फॉलो मी 3, runway 27 वर पक्षी आहेत, मी taxiway Charlie वर थांबलोय.", "VIDP", DEL, channel="airside")
    assert acts(r)[0][1] == "REPORT_BIRDS"


# ---- the Step-1 scorer itself (judge_full) ----
from scoring import judge_full

TWO = {"id": "t", "channel": "tower", "airport": "VIDP", "action": "two_runways", "phase": {"IGO5134": "ground"},
       "traffic": ["IGO5134", "AIC2817"],
       "truth": {"runway": "29R", "callsign": "IGO5134", "instructions": [["29R", "CROSS"], ["29L", "HOLD_SHORT"]],
                 "call_actions": [], "conditional": False}}


def test_judge_two_runways_ok():
    assert judge_full(TWO, "IFLY 5134, cross runway 29R, hold short runway 29L.")[0] == "OK"


def test_judge_lost_second_runway_is_wrong():
    # the hold-short half vanished: what is shown is incomplete, so it must count as dangerous
    o, r = judge_full(TWO, "IFLY 5134, cross runway 29R.")
    assert o == "WRONG" and "runway 29L missing" in r["why_wrong"]


def test_judge_swapped_instructions_are_wrong():
    assert judge_full(TWO, "IFLY 5134, hold short runway 29R, cross runway 29L.")[0] == "WRONG"


def test_judge_go_around_without_runway_is_ok():
    it = dict(TWO, action="go_around", phase={"IGO5134": "air"},
              truth={"runway": None, "callsign": "IGO5134", "instructions": [], "call_actions": ["GO_AROUND"], "conditional": False})
    assert judge_full(it, "IFLY 5134, go around, I say again, go around.")[0] == "OK"


def test_judge_lost_condition_is_wrong():
    it = dict(TWO, action="conditional",
              truth={"runway": "27", "callsign": "IGO5134", "instructions": [["27", "LINEUP"]], "call_actions": [], "conditional": True})
    assert judge_full(it, "IFLY 5134, line up and wait runway 27.")[0] == "WRONG"
    assert judge_full(it, "IFLY 5134, behind the landing Airbus, line up and wait runway 27, behind.")[0] == "AMBER"


# ---- fixes from the step1 audio run (31 Oct) ----

def test_clipped_going_around_is_amber_go_around():
    r = analyse("Heading around, Air India 7293.", "VIDP", {"AIC7293"})
    assert r["call_actions"] == ["GO_AROUND"] and r["status"] == "PROBABLE"


def test_same_runway_twice_with_different_instructions_is_flagged():
    r = analyse("Ascend runway 29 left, holding short runway 29 left. Air India 9043.", "VIDP", {"AIC9043"})
    assert r["status"] == "FLAGGED"


def test_shared_flight_number_resolved_by_partial_airline_word():
    T = {"AIC4822", "IGO4822", "AKJ8795"}
    r = analyse("Taxi to holding point, runway 09, via Bravo, IFL 4822.", "VABB", T)
    assert r["callsign"] == "IGO4822" and r["status"] == "PROBABLE"
    # no hint at all -> still refused
    assert analyse("Taxi to holding point, runway 09, via Bravo, 4822.", "VABB", T)["callsign"] is None



# ---- permanent guard: a pilot's clearly heard WRONG callsign must never become OK or AMBER ----

def test_wrong_readback_callsign_is_never_hidden():
    # dev d002b, clean audio: tower cleared Air India 9158; the pilot really said 9118.
    it = {"id": "d002b", "channel": "pilot", "airport": "VABB", "action": "hold",
          "traffic": ["AIC9158", "AKJ1111", "IGO2222"], "traps": ["wrong_readback_callsign"],
          "truth": {"runway": "32", "callsign": "AIC9118"}}
    for heard in ["Holding short, runway 32, Air India 9118.", "Holding short runway 32, Air India 9118"]:
        o, r = judge_full(it, heard)
        assert r["status"] == "FLAGGED" and o == "OK", heard     # OK here = "correctly flagged"