"""How a call is heard: the hazard-vocabulary hint is used only on vehicle calls listen 1 did not understand."""
from sentinel_pipeline import hear
from sentinel_state import RunwayEngine


def _fake(first, hinted_text):
    calls = []

    def stt(path, ch, fmt="transcribe", extra_keyterms=None, previous_text=None):
        calls.append((fmt, bool(extra_keyterms)))
        return hinted_text if extra_keyterms else first
    return stt, calls


def test_default_hint_is_v2_after_a11():
    import sentinel_pipeline
    assert sentinel_pipeline.HINT_MODE == "v2"
    stt, calls = _fake("Tower bird chaser 2, runway 27 वर पक्की आहे.", "Tower bird chaser 2, runway 27 वर पक्षी आहे.")
    h = hear("x.wav", "airside", "VABB", {"BIRDCHASER2", "AIC657"}, stt)
    assert h["hinted"] and calls == [("transcribe", False), ("transcribe", True)]
    stt, calls = _fake("Tower bird chaser 2, runway 27 वर पक्की आहे.", "x")
    assert not hear("x.wav", "airside", "VABB", {"BIRDCHASER2"}, stt, hint_mode="off")["hinted"]


def test_v1_hint_used_for_a_not_understood_vehicle_call():
    stt, calls = _fake("Tower bird chaser 2, runway 27 वर पक्की आहे.", "Tower bird chaser 2, runway 27 वर पक्षी आहे.")
    h = hear("x.wav", "airside", "VABB", {"BIRDCHASER2", "AIC657"}, stt, hint_mode="v1")
    assert h["hinted"] and "पक्षी" in h["text"] and calls == [("transcribe", False), ("transcribe", True)]


def test_hint_never_asked_for_an_understood_request():
    # A8: hinting this kind of call once inserted "पक्षी" into a crossing request. Now not even asked (no cost, no wait)
    stt, calls = _fake("Our following five runway 27 cross runway holding point Bravo 3.", "x पक्षी")
    for mode in ("v1", "v2"):
        h = hear("x.wav", "airside", "VIDP", {"FOLLOWME5"}, stt, hint_mode=mode)
        assert not h["hinted"] and "पक्षी" not in h["text"]
    assert all(not hinted for _, hinted in calls)


def test_hint_never_used_on_tower_or_pilot_calls():
    stt, calls = _fake("Sing runway 29, right with Tara 926.", "whatever")
    hear("x.wav", "pilot", "VIDP", {"VTI926"}, stt, hint_mode="v2")
    assert calls == [("transcribe", False)]


def test_v2_rejects_a_hint_that_loses_the_vehicle_listen_1_heard():
    # A9 a9A_Avinash_1 5 dB, exact transcripts: v1 took it and lost "bird chaser 2" (AMBER -> FLAG)
    l1 = "Tower bird chaser 2, runway 09, work up here. Please activate Charlie's word 11."
    hint = "Our bird chaser team, runway 09, were पक्षी आहे. Please activate Charlie's bird signal."
    traffic = {"BIRDCHASER2", "BIRDCHASER4", "AIC657"}
    assert hear("x.wav", "airside", "VABB", traffic, _fake(l1, hint)[0], hint_mode="v1")["hinted"]
    h = hear("x.wav", "airside", "VABB", traffic, _fake(l1, hint)[0], hint_mode="v2")
    assert not h["hinted"] and h["hint_rejected"] and h["text"] == l1


def test_v2_keeps_a_hint_that_names_the_same_vehicle():
    # A9 a9A_Riyaa_0 10 dB, exact transcripts
    l1 = "Our bird chaser 5, runway 09, were parked here. Please taxiway Charlie 100."
    hint = "हॉट Bird Chaser 5, runway 09 वर पक्षी आहेत, please taxiway Charlie 1 वर थांबवा."
    h = hear("x.wav", "airside", "VABB", {"BIRDCHASER5", "BIRDCHASER2", "AIC657"}, _fake(l1, hint)[0], hint_mode="v2")
    assert h["hinted"] and "पक्षी" in h["text"]


def test_hinted_bird_report_is_red_and_labelled():
    e = RunwayEngine("VABB", {"AIC657", "BIRDCHASER2"}, {"AIC657": "ground"})
    e.call(0, "tower", "Air India 657, runway 27, cleared for takeoff.")
    r = e.call(15, "airside", "Tower bird chaser 2, runway 27 वर पक्षी आहे.", hinted=True)
    red = [a for a in r["alerts"] if a["level"] == "RED"]
    assert red and red[0]["kind"] == "BIRDS_ON_ACTIVE_RUNWAY" and "hazard-word hint" in red[0]["text"]
    assert r["analysis"]["status"] != "CONFIRMED"


# ---- speculative verbatim listen (latency fix, 4 Nov) ----
def _glued_stt(delay=0.0):
    import time
    calls = []

    def stt(path, ch, fmt="transcribe", extra_keyterms=None, previous_text=None):
        time.sleep(delay)
        calls.append(fmt)
        # the BOM t=40 case: niner glued into the callsign by listen 1, words in verbatim
        return ("Runway 27, cleared to land, IFLY three six zero five three." if fmt == "verbatim"
                else "Runway 27, cleared to land, IFLY 36053.")
    return stt, calls


def test_speculative_gives_exactly_the_serial_result():
    keys = ("first", "text", "text2", "hinted", "verbatim_used")
    for ch, traffic in (("pilot", {"IGO3653", "AIC657"}), ("tower", {"AIC657"}), ("airside", {"BIRDCHASER2"})):
        s1, _ = _glued_stt()
        s2, _ = _glued_stt()
        a = hear("x.wav", ch, "VABB", traffic, s1, speculative=False)
        b = hear("x.wav", ch, "VABB", traffic, s2, speculative=True)
        assert {k: a[k] for k in keys} == {k: b[k] for k in keys}


def test_speculative_removes_the_wait_for_a_glued_callsign():
    import time
    stt, calls = _glued_stt(0.3)
    t0 = time.perf_counter()
    h = hear("x.wav", "pilot", "VABB", {"IGO3653"}, stt, speculative=True)
    took = time.perf_counter() - t0
    assert h["verbatim_used"] and h["text2"] and sorted(calls) == ["transcribe", "verbatim"]
    assert took < 0.5                     # two 0.3 s Prisma calls, side by side, not one after the other


def test_serial_mode_asks_verbatim_only_when_needed():
    stt, calls = _fake("Air India 657, runway 27, cleared for takeoff.", "x")
    h = hear("x.wav", "tower", "VABB", {"AIC657"}, stt, speculative=False)
    assert calls == [("transcribe", False)] and h["text2"] is None and not h["verbatim_used"]
