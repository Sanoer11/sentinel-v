"""How a call is heard: the hazard-vocabulary hint is used only on vehicle calls listen 1 did not understand."""
from sentinel_pipeline import hear
from sentinel_state import RunwayEngine


def _fake(first, hinted_text):
    calls = []

    def stt(path, ch, fmt="transcribe", extra_keyterms=None, previous_text=None):
        calls.append((fmt, bool(extra_keyterms)))
        return hinted_text if extra_keyterms else first
    return stt, calls


def test_hint_used_for_a_not_understood_vehicle_call():
    stt, calls = _fake("Tower bird chaser 2, runway 27 वर पक्की आहे.", "Tower bird chaser 2, runway 27 वर पक्षी आहे.")
    h = hear("x.wav", "airside", "VABB", {"BIRDCHASER2", "AIC657"}, stt)
    assert h["hinted"] and "पक्षी" in h["text"] and calls == [("transcribe", False), ("transcribe", True)]


def test_hint_never_asked_for_an_understood_request():
    # A8: hinting this kind of call once inserted "पक्षी" into a crossing request
    stt, calls = _fake("Our following five runway 27 cross runway holding point Bravo 3.", "x पक्षी")
    h = hear("x.wav", "airside", "VIDP", {"FOLLOWME5"}, stt)
    assert not h["hinted"] and calls == [("transcribe", False)]


def test_hint_never_used_on_tower_or_pilot_calls():
    stt, calls = _fake("Sing runway 29, right with Tara 926.", "whatever")
    hear("x.wav", "pilot", "VIDP", {"VTI926"}, stt)
    assert calls == [("transcribe", False)]


def test_hinted_bird_report_is_red_and_labelled():
    e = RunwayEngine("VABB", {"AIC657", "BIRDCHASER2"}, {"AIC657": "ground"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    r = e.call(15, "airside", "Tower bird chaser 2, runway 27 वर पक्षी आहे.", hinted=True)
    red = [a for a in r["alerts"] if a["level"] == "RED"]
    assert red and red[0]["kind"] == "BIRDS_ON_ACTIVE_RUNWAY" and "hazard-word hint" in red[0]["text"]
    assert r["analysis"]["status"] != "CONFIRMED"
