"""
Step 2 tests: runway state engine + readback check. Scenarios are written as radio text.
Run:  python -m pytest -q test_state.py
"""
from sentinel_state import RunwayEngine, strip_of


def reds(alerts):
    return [a for a in alerts if a["level"] == "RED"]


# ---- physical model ----

def test_both_ends_are_one_strip():
    assert strip_of("VIDP", "29R") == strip_of("VIDP", "11L") == "11L/29R"
    assert strip_of("VIDP", "29R") != strip_of("VIDP", "29L")


# ---- the two real Indian incidents this project is built on ----

def test_delhi_aug_2023_cross_while_takeoff():
    # VTI725 cleared for take-off 29R; VTI926 (landed 29L) told to cross 29R
    T = {"VTI725", "VTI926"}
    e = RunwayEngine("VIDP", T, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "Vistara 725, runway 29 right, cleared for takeoff.")
    e.call(3, "pilot", "Runway 29 right, cleared for takeoff, Vistara 725.")
    r = e.call(20, "tower", "Vistara 926, cross runway 29 right.")
    assert any("RUNWAY CONFLICT on 11L/29R" in a["text"] and "VTI926" in a["text"] for a in reds(r["alerts"]))


def test_delhi_order_reversed_also_caught():
    T = {"VTI725", "VTI926"}
    e = RunwayEngine("VIDP", T, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "Vistara 926, cross runway 29 right.")
    r = e.call(15, "tower", "Vistara 725, runway 29 right, cleared for takeoff.")
    assert reds(r["alerts"])


def test_mumbai_jun_2024_land_while_takeoff():
    # AI657 cleared for take-off 27; IndiGo 6053 cleared to land 27 before it was airborne
    T = {"AIC657", "IGO6053"}
    e = RunwayEngine("VABB", T, {"AIC657": "ground", "IGO6053": "air"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    r = e.call(30, "tower", "IFLY 6053, runway 27, cleared to land.")
    assert any("27" in a["text"] and "AIC657" in a["text"] for a in reds(r["alerts"]))


def test_mumbai_crossing_runways_checked_together():
    T = {"AIC657", "IGO6053"}
    e = RunwayEngine("VABB", T, {"AIC657": "ground", "IGO6053": "air"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    r = e.call(30, "tower", "IFLY 6053, runway 32, cleared to land.")
    assert any("crosses" in a["text"] for a in reds(r["alerts"]))


# ---- normal traffic must NOT alarm ----

def test_normal_sequence_no_alarm():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "Air India 2817, runway 28, cleared for takeoff.")
    e.call(3, "pilot", "Runway 28, cleared for takeoff, Air India 2817.")
    r = e.call(200, "tower", "IFLY 5134, runway 28, cleared to land.")      # departure long gone
    assert not reds(r["alerts"]) and not reds(e.alerts)


def test_conditional_lineup_behind_landing_is_allowed():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    r = e.call(20, "tower", "Air India 2817, behind the landing Airbus, line up and wait runway 28, behind.")
    assert not reds(r["alerts"])


def test_unconditional_lineup_while_landing_is_red():
    # the Haneda Jan 2024 shape: something on the runway while another aircraft is cleared to land
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    r = e.call(20, "tower", "Air India 2817, line up and wait runway 28.")
    assert reds(r["alerts"])


def test_go_around_releases_the_runway():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    e.call(30, "tower", "IFLY 5134, go around, I say again, go around.")
    r = e.call(40, "tower", "Air India 2817, cross runway 28.")
    assert not any(a["kind"] == "RUNWAY_CONFLICT" for a in r["alerts"])


def test_parallel_runways_do_not_conflict():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 29 left, cleared to land.")
    r = e.call(10, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    assert not reds(r["alerts"])


# ---- readback check (only what was heard; never filled from the tower's words) ----

def _one(text_tower, text_pilot, T, phases, ap="VABB"):
    e = RunwayEngine(ap, T, phases)
    e.call(0, "tower", text_tower)
    r = e.call(4, "pilot", text_pilot)
    return e.pending[-1].get("verdict"), r["alerts"]


def test_correct_readback_matches():
    v, al = _one("Air India 9158, hold short runway 32.", "Holding short runway 32, Air India 9158.",
                 {"AIC9158"}, {"AIC9158": "ground"})
    assert v == "MATCH" and not al


def test_wrong_callsign_readback_is_red():
    # dev d002b, clean audio: pilot really said 9118
    v, al = _one("Air India 9158, hold short runway 32.", "Holding short, runway 32, Air India 9118.",
                 {"AIC9158"}, {"AIC9158": "ground"})
    assert v == "MISMATCH" and "CALLSIGN MISMATCH" in reds(al)[0]["text"]


def test_lost_last_digit_is_incomplete_not_wrong():
    v, al = _one("Air India 7753, cross runway 11 right, hold short runway 11 left.",
                 "Crossing runway 11 right, holding short runway 11 left. Air India 775.",
                 {"AIC7753"}, {"AIC7753": "ground"}, ap="VIDP")
    assert v == "INCOMPLETE" and "775_" in al[0]["text"] and al[0]["level"] == "AMBER"


def test_wrong_side_readback_is_red():
    v, al = _one("IFLY 5134, cross runway 29 right.", "Crossing runway 29 left, IFLY 5134.",
                 {"IGO5134"}, {"IGO5134": "ground"}, ap="VIDP")
    assert v == "MISMATCH" and "RUNWAY MISMATCH" in reds(al)[0]["text"]


def test_hold_short_read_back_as_cross_is_red_and_checks_conflict():
    T = {"IGO5134", "AIC2817"}
    e = RunwayEngine("VIDP", T, {"IGO5134": "ground", "AIC2817": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    e.call(3, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(10, "tower", "IFLY 5134, hold short runway 29 right.")
    r = e.call(14, "pilot", "Crossing runway 29 right, IFLY 5134.")
    txt = " | ".join(a["text"] for a in reds(r["alerts"]))
    assert "INSTRUCTION MISMATCH" in txt and "IF IGO5134 DOES WHAT IT READ BACK" in txt


def test_stop_not_confirmed_is_red():
    # step1 s004b: "Stopping" heard as "Wing"
    v, al = _one("Akasa Air 2612, stop immediately, I say again, stop immediately.", "Wing Akasa Air 2612.",
                 {"AKJ2612"}, {"AKJ2612": "ground"})
    assert v == "INCOMPLETE" and al[0]["level"] == "RED" and "STOP not confirmed" in al[0]["text"]


def test_condition_not_read_back():
    v, al = _one("Air India 3449, behind the landing Airbus, line up and wait runway 27, behind.",
                 "Line up and wait runway 27, Air India 3449.", {"AIC3449"}, {"AIC3449": "ground"})
    assert v == "INCOMPLETE" and "condition" in al[0]["text"]


def test_no_readback_alert():
    e = RunwayEngine("VABB", {"AKJ2612"}, {"AKJ2612": "ground"})
    e.call(0, "tower", "Akasa Air 2612, stop immediately, I say again, stop immediately.")
    al = e.tick(15)
    assert al and al[0]["kind"] == "NO_READBACK" and al[0]["level"] == "RED"


# ---- vehicles ----

def test_vehicle_request_on_occupied_runway():
    T = {"IGO5134", "FOLLOWME3"}
    e = RunwayEngine("VIDP", T, {"IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    r = e.call(30, "airside", "Tower, Follow Me 3, runway 28 cross karna hai, Bravo pe hold kar raha hoon.")
    assert any(a["kind"] == "VEHICLE_REQUEST_OCCUPIED" for a in r["alerts"])


def test_birds_on_active_runway_is_red():
    T = {"AIC657", "BIRDCHASER2"}
    e = RunwayEngine("VABB", T, {"AIC657": "ground"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    r = e.call(20, "airside", "टॉवर, बर्ड चेसर टू, रनवे टू सेवन वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय.")
    assert reds(r["alerts"]) and reds(r["alerts"])[0]["kind"] == "BIRDS_ON_ACTIVE_RUNWAY"


def test_unclear_tower_call_never_produces_a_red_mismatch():
    # dev2 e012a/e012b 0dB: tower "cleared to land" was heard as "cleared for takeoff" (airborne aircraft),
    # pilot correctly read back "cleared to land". That is not a pilot error.
    e = RunwayEngine("VABB", {"IGO7981"}, {"IGO7981": "air"})
    e.call(0, "tower", "I fly 7981, runway 14, cleared for takeoff.")
    r = e.call(4, "pilot", "Cleared to land runway 14, IFLY 7981.")
    assert not reds(r["alerts"])


def test_tower_callsign_lost_readback_still_checked_for_runway():
    e = RunwayEngine("VIDP", {"IGO6710"}, {"IGO6710": "ground"})
    e.call(0, "tower", "I have a live, hold short runway 10.")
    r = e.call(4, "pilot", "Holding short runway 28, IFLY 6710.")
    assert any("RUNWAY MISMATCH" in a["text"] for a in r["alerts"])


# ---- second listen on a callsign mismatch (verbatim, no tower context) ----

def _mismatch_engine():
    e = RunwayEngine("VIDP", {"AIC8496"}, {"AIC8496": "ground"})
    e.call(0, "tower", "Air India 8496, hold short, runway 10.")
    rec = e.call(4, "pilot", "Holding short, runway 10, Air India 8498.")
    assert reds(rec["alerts"])
    return e, rec


def test_second_listen_with_cleared_number_demotes_to_amber():
    e, rec = _mismatch_engine()
    rec = e.recheck_readback(rec, "Holding short runway one zero, Air India eight four niner six.")
    assert not reds(rec["alerts"]) and "listen 2 heard AIC8496" in rec["alerts"][0]["text"]


def test_same_wrong_number_twice_stays_red():
    e, rec = _mismatch_engine()
    rec = e.recheck_readback(rec, "Holding short runway one zero, Air India eight four niner eight.")
    assert reds(rec["alerts"]) and "both listens" in reds(rec["alerts"])[0]["text"]


def test_second_listen_never_turns_a_mismatch_green():
    e, rec = _mismatch_engine()
    rec = e.recheck_readback(rec, "Holding short runway one zero, Air India eight four niner six.")
    assert e.pending[-1]["verdict"] != "MATCH"


# ---- surveillance hook: Haneda Jan 2024 shape ----

def test_runway_entry_without_clearance_is_incursion():
    T = {"JAL516", "JCG1", "AIC2817"}
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"IGO5134": "air", "AIC2817": "ground"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    e.call(5, "tower", "Air India 2817, taxi to holding point runway 28 via Bravo.")
    al = e.observed_on_runway(40, "AIC2817", "28")
    kinds = {a["kind"] for a in al}
    assert "INCURSION" in kinds and "RUNWAY_CONFLICT" in kinds


def test_second_listen_with_no_number_keeps_red():
    e, rec = _mismatch_engine()
    rec = e.recheck_readback(rec, "Holding short runway one zero, Air India.")
    assert reds(rec["alerts"])


def test_runway_vacated_report_frees_the_runway():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "air"})
    e.call(0, "tower", "IFLY 5134, runway 28, cleared to land.")
    e.call(4, "pilot", "Cleared to land runway 28, IFLY 5134.")
    e.call(90, "pilot", "Runway vacated, IFLY 5134.")
    r = e.call(100, "tower", "Air India 2817, runway 28, cleared for takeoff.")
    assert not reds(r["alerts"])


def test_glued_number_second_listen_does_not_soften_a_readback_mismatch():
    # the verbatim second listen made for glued numbers must not be reused to soften a callsign mismatch (A6 failed)
    e = RunwayEngine("VIDP", {"AIC8496"}, {"AIC8496": "ground"})
    e.call(0, "tower", "Air India 8496, hold short, runway 10.")
    r = e.call(4, "pilot", "Holding short, runway 10, Air India 8498.",
               second_text="Holding short runway one zero, Air India eight four niner six.")
    assert reds(r["alerts"])


# ---- 10 dB scenario run (3 Nov) fixes ----

def test_unidentified_clearance_still_enters_the_picture_and_is_named_by_readback():
    # BOM_2024 at 10 dB: "IFLY 6053" heard as "36053" -> landing clearance with no callsign
    T = {"AIC657", "IGO6053"}
    e = RunwayEngine("VABB", T, {"AIC657": "ground", "IGO6053": "air"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    e.call(4, "pilot", "Runway 27 cleared for takeoff, Air India 657.")
    r1 = e.call(40, "tower", "36053, runway 27, cleared to land.")
    assert any(a["kind"] == "RUNWAY_CONFLICT" and a["level"] == "AMBER" for a in r1["alerts"])
    r2 = e.call(44, "pilot", "Cleared to land, runway 27. IFLY, 6053.")
    assert any(a["kind"] == "RUNWAY_CONFLICT" and "IGO6053" in a["text"] for a in reds(r2["alerts"]))


def test_report_vacated_heard_wrong_still_frees_the_runway():
    # NORMAL_DEL at 10 dB: "Runway vacated" heard as "Report vacated"
    T = {"IGO5134", "AKJ1123"}
    e = RunwayEngine("VIDP", T, {"IGO5134": "air", "AKJ1123": "ground"})
    e.call(40, "tower", "IFLY 5134, runway 29 left, cleared to land.")
    e.call(44, "pilot", "Cleared to land runway 29 left, IFLY 5134.")
    e.call(150, "pilot", "Report vacated. IFLY 5134.")
    r = e.call(160, "tower", "Akasa Air 1123, runway 29 left, cleared for takeoff.")
    assert not reds(r["alerts"])


def test_crossing_readback_with_report_vacated_is_not_a_vacated_report():
    T = {"IGO5134"}
    e = RunwayEngine("VIDP", T, {"IGO5134": "ground"})
    e.call(0, "tower", "IFLY 5134, cross runway 28, report vacated.")
    r = e.call(4, "pilot", "Crossing runway 28, will report vacated, IFLY 5134.")
    assert not any(a["kind"] == "VACATED" for a in r["alerts"]) and e.pending[-1]["verdict"] == "MATCH"


def test_call_naming_a_busy_runway_without_instruction_warns():
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    r = e.call(19, "pilot", "Asking runway 29 right, IFLY 5134.")
    assert any(a["kind"] == "RUNWAY_IN_USE_UNCLEAR" for a in r["alerts"])


def test_clipped_crossing_readback_with_report_vacated_does_not_free_runway():
    # "Crossing runway 28, will report vacated" with "Crossing" clipped -> must stay a readback
    T = {"IGO5134", "AIC2817"}
    e = RunwayEngine("VIDP", T, {"IGO5134": "ground", "AIC2817": "ground"})
    e.call(0, "tower", "IFLY 5134, cross runway 28, report vacated.")
    r = e.call(4, "pilot", "Taxiway runway 28, will report vacated, IFLY 5134.")
    assert not any(a["kind"] == "VACATED" for a in r["alerts"])
    r2 = e.call(10, "tower", "Air India 2817, runway 28, cleared for takeoff.")
    assert reds(r2["alerts"])                       # the crossing is still in the picture


def test_aircraft_named_only_by_readback_with_lookalike_is_flagged():
    T = {"IGO6053", "IGO6035", "AIC657"}
    e = RunwayEngine("VABB", T, {"IGO6053": "air", "IGO6035": "air"})
    e.call(0, "tower", "36053, runway 27, cleared to land.")
    r = e.call(4, "pilot", "Cleared to land runway 27, IFLY 6035.")
    assert any(a["kind"] == "NAMED_BY_READBACK_ONLY" for a in r["alerts"])