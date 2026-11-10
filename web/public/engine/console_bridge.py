"""Tower console bridge: lets the page drive the real RunwayEngine (sentinel_state.py) inside the browser.

The engine files next to this one are byte-for-byte copies of the ones at the repo root (CI checks that).
Nothing here decides anything: it only passes typed calls in and turns the engine's answers into JSON.
"""
import json
import sys
import types

try:
    import numpy  # noqa: F401
except ImportError:
    # sentinel_voice needs numpy only to join audio samples; the page plays the recorded clips itself,
    # so here it is asked only WHICH alert is spoken and with which phrases.
    sys.modules["numpy"] = types.ModuleType("numpy")
import sentinel_voice
from sentinel_state import RunwayEngine

ENG = None


def _alerts(alerts):
    return [{"level": a["level"], "kind": a["kind"], "text": a["text"]} for a in alerts]


def _spoken(alerts):
    a = sentinel_voice.pick(alerts)
    return sentinel_voice.phrases(a) if a else None


def _picture(t):
    out = []
    for strip, occ in ENG.occ.items():
        for o in occ:
            if o["until"] > t:
                row = {"strip": strip, "cs": o["cs"], "action": o["action"], "rw": o["rw"], "left": int(round(o["until"] - t))}
                if o.get("maybe"):
                    row["maybe"] = o["maybe"]
                out.append(row)
    return out


def start(airport, traffic_json):
    global ENG
    ENG = RunwayEngine(airport, json.loads(traffic_json))
    return json.dumps({"ok": True})


def set_traffic(traffic_json):
    ENG.traffic = set(json.loads(traffic_json))
    return json.dumps({"ok": True})


def call(t, channel, text):
    rec = ENG.call(t, channel, text)
    a = rec["analysis"]
    return json.dumps({
        "status": a["status"], "read": a["callsign"],
        "instructions": [{"runway": x["runway"], "action": x["action"]} for x in a["instructions"]],
        "notes": list(a["problems"]) + list(a["amber"]),
        "alerts": _alerts(rec["alerts"]), "spoken": _spoken(rec["alerts"]), "picture": _picture(t),
    }, ensure_ascii=False)


def tick(t):
    ENG._prune(t)
    new = ENG.tick(t)
    return json.dumps({"alerts": _alerts(new), "spoken": _spoken(new), "picture": _picture(t)}, ensure_ascii=False)
