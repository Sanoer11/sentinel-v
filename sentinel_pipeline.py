"""
One place that decides how a radio call is HEARD (used by run_eval, run_scenarios and the live demo).

  listen 1   Prisma transcribe, general ATC keyterms                       - always
  listen 2   Prisma verbatim, same audio, no tower context                 - only for glued numbers (Fix G/N)
                                                                              and vehicle numbers (A4)
  hint       Prisma transcribe + hazard vocabulary (पक्षी, birds, FOD)     - vehicle channel only, and only
             when listen 1 understood NO request/report for any real runway (Experiment A8)

Why the hint is this narrow (A8, 3 Nov, 124 vehicle clips): hinting EVERY vehicle call brought back 5 of 10
lost bird reports, but also changed 5 lines for the worse and once inserted "पक्षी" into a crossing request.
Every one of the 5 bird recoveries came from a call listen 1 had NOT understood; none of the 5 worse lines
or the inserted word did. That split was found AFTER the run, so it is confirmed only on new audio
(human Marathi recordings / the locked exam's unseen Marathi voice).
"""
import time
import sentinel_parse
import sentinel_actions

HAZARD_TERMS = ["पक्षी", "पक्षी आहेत", "birds", "bird activity", "FOD"]
HAZARD_HINT = True


def _understood(text, airport, traffic, channel):
    a = sentinel_actions.analyse(text, airport, traffic, channel)
    return any(x["valid"] and x["action"] and not x["conflict"] for x in a["instructions"])


def hear(path, channel, airport, traffic, stt):
    t0 = time.perf_counter()
    text = stt(path, channel)
    out = {"first": text, "text": text, "text2": None, "hinted": False}
    if HAZARD_HINT and channel == "airside" and not _understood(text, airport, traffic, channel):
        th = stt(path, channel, extra_keyterms=HAZARD_TERMS)
        out["hint_text"] = th
        if _understood(th, airport, traffic, channel):
            out["text"], out["hinted"] = th, True
    first = sentinel_parse.extract(out["text"], airport, set(traffic))
    if (sentinel_parse.needs_second_listen(first)
            or (sentinel_parse.NINER_GLUE_FIX and sentinel_parse.needs_callsign_second_listen(first))
            or sentinel_parse.needs_vehicle_second_listen(first, set(traffic))
            or (sentinel_actions.INSTRUCTION_SECOND_LISTEN
                and sentinel_actions.needs_instruction_second_listen(first["normalized"], airport, channel))):
        out["text2"] = stt(path, channel, fmt="verbatim")
    out["latency_s"] = time.perf_counter() - t0
    return out
