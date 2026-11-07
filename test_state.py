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
    # LAND (airborne) vs TAKEOFF (on the ground) cannot be one aircraft: RED on time.
    # Since A15 (Fix S) the glued "36053" already names IGO6053 at the tower call, so the RED names it at once.
    assert any(a["kind"] == "RUNWAY_CONFLICT" and a["level"] == "RED" and "IGO6053" in a["text"] for a in r1["alerts"])
    r2 = e.call(44, "pilot", "Cleared to land, runway 27. IFLY, 6053.")
    assert not reds(r2["alerts"])                       # the matching readback adds no second alarm
    import sentinel_parse
    sentinel_parse.SUFFIX_CALLSIGN = False              # the old path (unidentified, named by its readback) still works
    try:
        e = RunwayEngine("VABB", T, {"AIC657": "ground", "IGO6053": "air"})
        e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
        e.call(4, "pilot", "Runway 27 cleared for takeoff, Air India 657.")
        r1 = e.call(40, "tower", "36053, runway 27, cleared to land.")
        assert any(a["kind"] == "RUNWAY_CONFLICT" and a["level"] == "RED" for a in r1["alerts"])
        r2 = e.call(44, "pilot", "Cleared to land, runway 27. IFLY, 6053.")
        assert any(a["kind"] == "RUNWAY_CONFLICT" and "IGO6053" in a["text"] for a in reds(r2["alerts"]))
    finally:
        sentinel_parse.SUFFIX_CALLSIGN = True


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
    import sentinel_parse
    sentinel_parse.SUFFIX_CALLSIGN = False              # tower callsign not recovered: named by the readback only
    try:
        e.call(0, "tower", "36053, runway 27, cleared to land.")
        r = e.call(4, "pilot", "Cleared to land runway 27, IFLY 6035.")
        assert any(a["kind"] == "NAMED_BY_READBACK_ONLY" for a in r["alerts"])
    finally:
        sentinel_parse.SUFFIX_CALLSIGN = True
    # A15 on: "36053" names IGO6053 (AMBER, look-alike noted), so the look-alike answering is a RED callsign mismatch
    e = RunwayEngine("VABB", T, {"IGO6053": "air", "IGO6035": "air"})
    e.call(0, "tower", "36053, runway 27, cleared to land.")
    r = e.call(4, "pilot", "Cleared to land runway 27, IFLY 6035.")
    assert any(a["level"] == "RED" and "CALLSIGN MISMATCH" in a["text"] for a in r["alerts"])


def test_readback_to_a_misunderstood_clearance_is_paired_but_never_matched():
    # HOLD_AS_CROSS 10 dB: "hold short runway 29 as well" (side lost)
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(15, "tower", "Flight 5134, hold short, runway 29 as well.")
    r = e.call(19, "pilot", "Asking runway 29 right, he flee 5134.")
    assert e.pending[-1]["verdict"] == "INCOMPLETE"          # paired, never MATCH
    assert any("HOLD SHORT not confirmed" in a["text"] for a in r["alerts"])


def test_busy_runway_amber_not_repeated_under_a_red_conflict():
    T = {"VTI725", "VTI926"}
    e = RunwayEngine("VIDP", T, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "Vistara 725, runway 29 right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Vistara 725.")
    e.call(25, "tower", "Vistara 926, cross runway 29 right.")
    r = e.call(29, "pilot", "Sing runway 29, right with Vistara 926.")
    assert not any(a["kind"] == "RUNWAY_IN_USE_UNCLEAR" for a in r["alerts"])



def test_unidentified_same_phase_clearance_is_only_possible_conflict():
    # two take-off clearances on 28, the first without a heard callsign: could be the same aircraft twice
    T = {"AIC2817"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground"})
    e.call(0, "tower", "Runway 28, cleared for takeoff.")
    r = e.call(30, "tower", "Air India 2817, runway 28, cleared for takeoff.")
    assert any(a["kind"] == "RUNWAY_CONFLICT" and a["level"] == "AMBER" for a in r["alerts"]) and not reds(r["alerts"])


def test_hold_short_not_confirmed_on_busy_runway_is_red():
    # HOLD_AS_CROSS at 10 dB: tower "hold short runway 29 as well" (side lost), pilot "Asking runway 29 right"
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(15, "tower", "Flight 5134, hold short, runway 29 as well.")
    r = e.call(19, "pilot", "Asking runway 29 right, he flee 5134.")
    red = reds(r["alerts"])
    assert red and "HOLD SHORT not confirmed" in red[0]["text"] and red[0]["rw"] == "29R"
    assert not any(a["kind"] == "RUNWAY_IN_USE_UNCLEAR" for a in r["alerts"])      # no duplicate amber


def test_hold_short_not_confirmed_on_free_runway_stays_amber():
    e = RunwayEngine("VIDP", {"IGO5134"}, {"IGO5134": "ground"})
    e.call(15, "tower", "IFLY 5134, hold short runway 29 right.")
    r = e.call(19, "pilot", "Asking runway 29 right, IFLY 5134.")
    assert not reds(r["alerts"])


def test_hold_short_read_back_as_crossing_stays_red_when_only_the_side_was_lost():
    # 4 Nov, HOLD_AS_CROSS at 10 dB, noise recordings 2 and 3: the exact transcripts
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(15, "tower", "Fly 5134, hold short, runway 29 as well.")
    r = e.call(19, "pilot", "Crossing runway 29, right? If please, 5134.")
    kinds = {(a["level"], a["kind"]) for a in r["alerts"]}
    assert ("RED", "READBACK_MISMATCH") in kinds and ("RED", "RUNWAY_CONFLICT") in kinds
    assert any("side not heard" in a["text"] for a in r["alerts"])          # still says what was not checked


def test_unclear_callsign_still_only_amber():
    # the callsign was lost in the tower call: a differing readback is NOT proof of a pilot error
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(15, "tower", "Hold short, runway 29 as well.")
    r = e.call(19, "pilot", "Crossing runway 29, right, IFLY 5134.")
    assert not any(a["kind"] == "READBACK_MISMATCH" for a in r["alerts"])


def test_runway_lost_in_tower_call_is_located_by_the_readback():
    # DEL_2023 10 dB noise recordings 1 and 2 (4 Nov), exact transcripts: tower runway glued (290), pilot's
    # "Runway" heard as "Taxiway" -> before: no conflict when VTI926 was cleared to cross 29R
    import sentinel_actions
    sentinel_actions.TAXIWAY_AS_RUNWAY = True          # needed for this pilot transcript; OFF by default (A12 T1)
    try:
        _located_case()
    finally:
        sentinel_actions.TAXIWAY_AS_RUNWAY = False


def _located_case():
    for t0 in ("ARF 725, runway 290, right. Cleared for takeoff.", "775, runway 290, right. Cleared for takeoff."):
        e = RunwayEngine("VIDP", {"VTI725", "VTI926", "AIC2817"}, {"VTI725": "ground", "VTI926": "ground"})
        e.call(0, "tower", t0)
        r = e.call(4, "pilot", "Taxiway 2, niner right, cleared for takeoff, Vistara 725.")
        assert any("tower's runway not heard; readback says 29R, not cross-checked" in a["text"] for a in r["alerts"])
        assert not any(a["level"] == "RED" for a in r["alerts"])           # nothing contradicts: AMBER, not RED
        r = e.call(25, "tower", "Tara, 926, cross runway 29 right.")
        red = [a for a in r["alerts"] if a["level"] == "RED"]
        assert red and red[0]["kind"] == "RUNWAY_CONFLICT" and "cleared 25 s ago" in red[0]["text"]


def test_taxiway_word_is_never_read_as_runway_without_a_runway_only_clearance():
    from sentinel_actions import analyse
    tr = {"IGO5134", "AIC657"}
    a = analyse("To land runway 2, niner left, taxiway 5134.", "VIDP", tr, "pilot")       # has 'runway' already
    assert not any("heard as 'taxiway'" in x for x in a["amber"])
    a = analyse("IFLY 5134, taxi via taxiway Bravo 4, hold short runway 28.", "VIDP", tr, "tower")
    assert not any("heard as 'taxiway'" in x for x in a["amber"])
    a = analyse("Tower bird chaser 2, runway 27 वर पक्षी आहे. मी taxiway 40 वर थांबलो.", "VABB", {"BIRDCHASER2"}, "airside")
    assert not any("heard as 'taxiway'" in x for x in a["amber"])
    import sentinel_actions
    sentinel_actions.TAXIWAY_AS_RUNWAY = True
    try:
        a = analyse("Taxiway 10, cleared for takeoff, Akasa Air 2612.", "VAPO", {"AKJ2612"}, "pilot")
        assert any("heard as 'taxiway'" in x for x in a["amber"]) and a["instructions"][0]["runway"] == "10" \
            and a["status"] != "CONFIRMED"
    finally:
        sentinel_actions.TAXIWAY_AS_RUNWAY = False


def test_located_by_readback_with_a_real_runway_word():
    # Fix L on its own (Fix T off): tower runway lost, the readback SAYS "runway"
    e = RunwayEngine("VIDP", {"VTI725", "VTI926"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "ARF 725, runway 290, right. Cleared for takeoff.")
    e.call(4, "pilot", "Runway 2, niner right, cleared for takeoff, Vistara 725.")
    r = e.call(25, "tower", "Tara, 926, cross runway 29 right.")
    assert any(a["level"] == "RED" and a["kind"] == "RUNWAY_CONFLICT" for a in r["alerts"])


def test_lost_runway_located_by_a_readback_with_a_different_instruction_is_red():
    # HOLD_AS_CROSS 10 dB noise 5 (4 Nov), exact transcripts: tower runway glued "291", readback "Crossing 29 right"
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29, arrive, cleared for takeoff. Air India 2817.")
    e.call(15, "tower", "Fly 5134, hold short, runway 291.", "Fly five one three four, hold short, runway two nine as well.")
    r = e.call(19, "pilot", "Crossing runway 29, right? He, please. 5134.")
    kinds = {(a["level"], a["kind"]) for a in r["alerts"]}
    assert ("RED", "READBACK_MISMATCH") in kinds and ("RED", "RUNWAY_CONFLICT") in kinds


def test_lost_runway_not_located_when_readback_runway_does_not_fit_the_heard_digits():
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff. Air India 2817.")
    e.call(15, "tower", "Fly 5134, hold short, runway 291.")
    r = e.call(19, "pilot", "Crossing runway 28, IFLY 5134.")              # 28 does not start "291"
    assert not any(a["kind"] == "READBACK_MISMATCH" for a in r["alerts"])
    assert any("does not settle it" in a["text"] for a in r["alerts"])


def test_unidentified_crossing_whose_number_cannot_be_the_departure_is_red():
    # DEL_2023 10 dB noise 8 (4 Nov), exact transcripts: "Tara, 9826" and "Vistara 9 ..." cannot be VTI725
    e = RunwayEngine("VIDP", {"VTI725", "VTI926", "AIC2817"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "First 725, runway 2, 9er right, cleared for takeoff.")
    e.call(4, "pilot", "One way, 29er right, cleared for takeoff. Vistara 725.")
    e.call(25, "tower", "Tara, 9826, cross runway 298, right?")
    r = e.call(29, "pilot", "Crossing runway 29 right, Vistara 9 Tuesday.")
    assert any(a["level"] == "RED" and a["kind"] == "RUNWAY_CONFLICT" for a in r["alerts"])


def test_unidentified_that_could_be_the_same_aircraft_stays_amber():
    # "15725" could be a garbled "725": a second clearance for maybe the SAME aircraft is not a proven conflict
    from sentinel_state import _could_be, _heard_numbers
    for heard in ("15725", "7725", "775", "725"):
        assert _could_be({heard}, "VTI725")
    assert not _could_be({"9826"}, "VTI725") and not _could_be({"9"}, "VTI725")
    assert _could_be(set(), "VTI725")                                    # nothing heard -> could be
    assert _heard_numbers("Wind 270 degrees 12 knots, runway 29R, cleared to land.") == set()


def test_misheard_runway_digit_located_by_readback_one_digit_away():
    # HOLD_AS_CROSS 10 dB noise 10 and 14 (4 Nov): tower "runway 39" (said 29), readback "Crossing runway 29 right"
    for tw in ("Fly 5134, hold short, runway 39 as well.", "Fly 5134, hold short, runway 39 right."):
        e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
        e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
        e.call(4, "pilot", "Runway 29 right, cleared for takeoff. Air India 2817.")
        e.call(15, "tower", tw)
        r = e.call(19, "pilot", "Crossing runway 29, right? Kifley 5134.")
        kinds = {(a["level"], a["kind"]) for a in r["alerts"]}
        assert ("RED", "READBACK_MISMATCH") in kinds and ("RED", "RUNWAY_CONFLICT") in kinds
        assert any("heard as 39 (no such runway)" in a["text"] for a in r["alerts"])
    # a readback runway that is NOT one digit away does not locate it
    e = RunwayEngine("VIDP", {"AIC2817", "IGO5134"}, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff. Air India 2817.")
    e.call(15, "tower", "Fly 5134, hold short, runway 39 right.")
    r = e.call(19, "pilot", "Crossing runway 10, IFLY 5134.")
    assert not any(a["kind"] == "READBACK_MISMATCH" for a in r["alerts"])


def test_conflict_with_an_old_landing_says_no_vacated_report_was_heard():
    # NORMAL_DEL 10 dB noise 17 (5 Nov): "Runway vacated" heard as "Can we vacate it" -> RED stays, reason shown
    e = RunwayEngine("VIDP", {"IGO5134", "AKJ1123"}, {"IGO5134": "air", "AKJ1123": "ground"})
    e.call(40, "tower", "IFLY 5134, runway 29 left, cleared to land.")
    e.call(150, "pilot", "Can we vacate it, IFLY 5134?")
    r = e.call(160, "tower", "Akasa Air 1123, runway 29 left, cleared for takeoff.")
    red = [a for a in r["alerts"] if a["level"] == "RED"]
    assert red and "no 'runway vacated' heard from IGO5134" in red[0]["text"]


# ---- A14 Fix U: a runway heard glued and never located is kept as a "maybe" runway ----

def test_unlocated_glued_runway_gives_possible_conflict_amber():
    # DEL_2023 10 dB noise recording 1 (exact transcripts): runway glued in the tower call AND lost in the readback.
    # Before A14 the crossing looked safe (silent miss). Now: AMBER "possible", never RED (the runway is a guess).
    e = RunwayEngine("VIDP", {"VTI725", "VTI926", "AIC2817"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "ARF 725, runway 290, right. Cleared for takeoff.")
    e.call(4, "pilot", "Taxiway 2, niner right, cleared for takeoff, Vistara 725.")
    r = e.call(25, "tower", "Tara, 926, cross runway 29 right.")
    poss = [a for a in r["alerts"] if a["kind"] == "RUNWAY_CONFLICT_POSSIBLE"]
    assert poss and poss[0]["level"] == "AMBER" and "heard as '290R', could be 29R" in poss[0]["text"]
    assert not reds(r["alerts"])


def test_maybe_runway_never_hides_a_located_red():
    # DEL_2023 10 dB noise recording 13: the readback DID locate 29R -> the maybe entry must go, the RED must stay
    e = RunwayEngine("VIDP", {"VTI725", "VTI926", "AIC2817"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "Air India 725, runway 290, right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Vistara 725.")
    r = e.call(25, "tower", "Tara, 926, cross runway 2, 9 right.")
    assert any(a["kind"] == "RUNWAY_CONFLICT" and a["level"] == "RED" for a in r["alerts"])
    assert not any(a["kind"] == "RUNWAY_CONFLICT_POSSIBLE" for a in r["alerts"])


def test_maybe_runway_needs_glued_digits():
    # one runway digit heard ("runway 2"): could be anything - no maybe runway, no extra alarm
    e = RunwayEngine("VIDP", {"VTI725", "VTI926"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "F 725, runway 2 line up and wait, cleared for takeoff.")
    r = e.call(25, "tower", "Vistara 926, cross runway 29 right.")
    assert not any(a["kind"] == "RUNWAY_CONFLICT_POSSIBLE" for a in r["alerts"])


# ---- A15 Fix S: airline word glued onto the flight number as digits ----

def test_extra_leading_digits_give_the_flight_as_amber():
    from sentinel_parse import extract
    r = extract("36053, runway 27, cleared to land.", "VABB", {"IGO6053", "AIC657"})
    assert r["callsign"] == "IGO6053" and any("extra digits in front (36053)" in x for x in r["amber"])
    r = extract("15725, runway 2, 9er right, cleared for takeoff.", "VIDP", {"VTI725", "VTI926"})
    assert r["callsign"] == "VTI725"


def test_extra_digits_matching_two_flights_give_nothing():
    from sentinel_parse import extract
    # 35134 ends in 5134 AND in 134 -> two flights could fit: no callsign, never a guess
    r = extract("35134, hold short, runway 29 right.", "VIDP", {"IGO5134", "AIC134"})
    assert r["callsign"] is None
