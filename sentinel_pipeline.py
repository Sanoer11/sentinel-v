"""
One place that decides how a radio call is HEARD (used by run_eval, run_scenarios and the live demo).

  listen 1   Prisma transcribe, general ATC keyterms                       - always
  listen 2   Prisma verbatim, same audio, no tower context                 - only for glued numbers (Fix G/N)
                                                                              and vehicle numbers (A4)
  hint       Prisma transcribe + hazard vocabulary (पक्षी, birds, FOD)     - vehicle channel only, see HINT_MODE

HINT_MODE history (each rule fixed BEFORE its run):
  A8 (3 Nov, Zahira only): hint on every vehicle call -> 5/10 birds back but 5 lines worse. Narrowed AFTER the run
     to "only when listen 1 understood nothing" = "v1".
  A9 (4 Nov, 6 new Marathi voices): v1 brought back 9/11 lost bird reports, 0 false birds, but made 2 lines WORSE
     (it got the birds and lost the vehicle number listen 1 had: "bird chaser 2" -> "bird chaser team").
     Rule A4 said 0 worse -> FAIL -> HINT_MODE = "off".
  "v2" = v1 + the hint may only ADD, never REMOVE: if listen 1 named a vehicle, the hint must name the SAME one.
     On the A9 clips this keeps 7/11 birds and 0 worse - but that was seen AFTER A9, so v2 stays off until it
     passes A10 (new sentences, new noise) under the same fixed rules.
  A10 (4 Nov, 24 new Marathi lines x 10/5 dB): listen 1 lost the bird word in only 3 clips; v2 brought 2 back,
     0 worse, but 1 FALSE bird -> rule A3 FAIL -> stays "off". (That false bird came from listen 1 itself,
     "4 birds is a 5" = "Bird Chaser 5", not from the hint - logged as its own issue, see sentinel_actions.)
  A11 (4 Nov): that cause fixed and tested on its own (BIRDS_EN_STRICT, 385 transcripts). A10 re-heard with it,
     A10's rules UNCHANGED: lost 3, back 2, 0 false birds, 0 worse -> PASS -> HINT_MODE = "v2".
     Known limit: A1 had only 3 lost clips (the minimum). Human Marathi recordings + the locked exam are its next check.
Hint and listen 1 now run ONE AFTER the other (4 Nov: side-by-side calls hit the rate limit, 429, and each
retry waits 1.5 s - worse than the 0.5 s they saved). The hint costs time only on vehicle calls listen 1 did not understand.
"""
import time
import sentinel_parse
import sentinel_actions

HAZARD_TERMS = ["पक्षी", "पक्षी आहेत", "birds", "bird activity", "FOD"]
HINT_MODE = "v2"           # "off" | "v1" | "v2"   (A9: v1 FAILED rule A4; A10 -> A11 Part R: v2 PASSED)


def _understood(text, airport, traffic, channel):
    a = sentinel_actions.analyse(text, airport, traffic, channel)
    return any(x["valid"] and x["action"] and not x["conflict"] for x in a["instructions"])


def _vehicle_id(text, airport, traffic):
    return sentinel_parse.extract(text, airport, set(traffic))["callsign"]


def hear(path, channel, airport, traffic, stt, speculative=False, hint_mode=None):
    """speculative=True: the verbatim listen is started together with listen 1 and thrown away unless needed.
    Same audio -> same text (A6/A7), so the result is identical; only the waiting changes. 4 Nov: on this API
    key the two side-by-side calls hit the rate limit (429) so often that the median wait went 0.57 s -> 2.1 s.
    So it is OFF everywhere; it only helps with a higher request quota.
    CORRECTION (A11, 4 Nov): the same audio heard twice gave a different listen-1 text in 5 of 48 clips (4 only
    script/case: "बर्ड चेसर" vs "Bird Chaser"; 1 changed meaning: "bird chaser C" vs "Bird Chaser 3"). So
    "identical result" is true only most of the time. Another reason it stays off.
    hint_mode: None = use HINT_MODE."""
    mode = HINT_MODE if hint_mode is None else hint_mode
    t0 = time.perf_counter()
    verb_job = None
    if speculative:
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=1)
        verb_job = pool.submit(stt, path, channel, fmt="verbatim")
        pool.shutdown(wait=False)
    text = stt(path, channel)
    out = {"first": text, "text": text, "text2": None, "hinted": False, "verbatim_used": False}
    if mode in ("v1", "v2") and channel == "airside" and not _understood(text, airport, traffic, channel):
        th = stt(path, channel, extra_keyterms=HAZARD_TERMS)
        out["hint_text"] = th
        ok = _understood(th, airport, traffic, channel)
        if ok and mode == "v2":
            id1 = _vehicle_id(text, airport, traffic)
            ok = id1 is None or _vehicle_id(th, airport, traffic) == id1     # may add, never remove
            out["hint_rejected"] = not ok
        if ok:
            out["text"], out["hinted"] = th, True
    first = sentinel_parse.extract(out["text"], airport, set(traffic))
    if (sentinel_parse.needs_second_listen(first)
            or (sentinel_parse.NINER_GLUE_FIX and sentinel_parse.needs_callsign_second_listen(first))
            or sentinel_parse.needs_vehicle_second_listen(first, set(traffic))
            or (sentinel_actions.INSTRUCTION_SECOND_LISTEN
                and sentinel_actions.needs_instruction_second_listen(first["normalized"], airport, channel))):
        out["text2"] = verb_job.result() if verb_job is not None else stt(path, channel, fmt="verbatim")
        out["verbatim_used"] = True
    out["latency_s"] = time.perf_counter() - t0
    return out
