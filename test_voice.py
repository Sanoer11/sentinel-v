"""Step 3 tests: which clips each RED alert is built from. Run: python -m pytest -q test_voice.py"""
from sentinel_voice import phrases, sentence, pick
from sentinel_state import RunwayEngine


def spoken(alert):
    p = phrases(alert)
    return sentence(p) if p else None


def _del():
    e = RunwayEngine("VIDP", {"VTI725", "VTI926"}, {"VTI725": "ground", "VTI926": "ground"})
    e.call(0, "tower", "Vistara 725, runway 29 right, cleared for takeoff.")
    return e.call(25, "tower", "Vistara 926, cross runway 29 right.")


def test_conflict_says_runway_first_then_new_aircraft_then_other():
    s = spoken([a for a in _del()["alerts"] if a["level"] == "RED"][0])
    assert s == "Runway conflict, two niner right, Vistara niner two six"


def test_amber_is_never_spoken():
    assert phrases({"level": "AMBER", "kind": "RUNWAY_CONFLICT", "callsigns": [], "rw": "28", "text": ""}) is None


def test_unidentified_aircraft_is_spoken_as_such():
    s = spoken({"level": "RED", "kind": "RUNWAY_CONFLICT", "callsigns": ["IGO6053", "UNIDENTIFIED (cleared at t=40s)"],
                "rw": "27", "text": "RUNWAY CONFLICT"})
    assert s == "Runway conflict, two seven, IFLY six zero fife tree"


def test_icao_digit_words():
    s = spoken({"level": "RED", "kind": "NO_READBACK", "callsigns": ["AKJ3590"], "rw": None, "text": ""})
    assert s == "No readback, Akasa Air tree fife niner zero"


def test_vehicle_callsign():
    s = spoken({"level": "RED", "kind": "INCURSION", "callsigns": ["FOLLOWME3"], "rw": "28", "text": ""})
    assert s == "Runway incursion, two eight, Follow Me tree"


def test_one_voice_per_call_the_most_dangerous():
    # hold-short read back as crossing: mismatch + readback conflict -> only the conflict is spoken
    T = {"AIC2817", "IGO5134"}
    e = RunwayEngine("VIDP", T, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(15, "tower", "IFLY 5134, hold short runway 29 right.")
    r = e.call(19, "pilot", "Crossing runway 29 right, IFLY 5134.")
    assert spoken(pick(r["alerts"])) == "Readback conflict, two niner right, IFLY fife one tree four"


def test_word_fallback_when_phrase_not_prepared(tmp_path, monkeypatch):
    import numpy as np, soundfile as sf, sentinel_voice as v
    monkeypatch.setattr(v, "SEG_DIR", str(tmp_path))
    for k in v.all_segments():
        sf.write(v.word_path(k), 0.3 * np.sin(np.arange(4000) / 3), 16000)
    ms, dur, fb = v.assemble(["Runway conflict", "runway two eight"], str(tmp_path / "out.wav"))
    assert fb == ["Runway conflict", "runway two eight"]
    assert [p.split("/")[-1] for p in v._word_fallback("runway two eight")] == [f"w_runway_s{v.SPEED}.wav", f"d_2_s{v.SPEED}.wav", f"d_8_s{v.SPEED}.wav"]
    assert [p.split("/")[-1] for p in v._word_fallback("Runway conflict")] == [f"h_RUNWAY_CONFLICT_s{v.SPEED}.wav"]