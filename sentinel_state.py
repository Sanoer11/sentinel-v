"""
Sentinel-V Step 2 — the runway state engine.

It keeps, for every runway STRIP, who has been cleared onto it, and checks every pilot readback
against the clearance it answers. It only uses what was heard; it never fills a gap from the
tower's words (that was proven circular on 1 Nov: it hid 4 wrong readbacks).

    eng = RunwayEngine("VIDP", traffic, phases)
    eng.call(t=0,  channel="tower", text="Vistara 725, runway 29R, cleared for takeoff")
    eng.call(t=20, channel="tower", text="Vistara 926, cross runway 29R")
    -> RED  RUNWAY CONFLICT on 11L/29R: VTI926 CROSS while VTI725 TAKEOFF (cleared 20 s ago)

Physical facts used
  - A runway has two ends: 29R and 11L are the SAME strip of concrete (opposite directions).
  - Mumbai's two runways 09/27 and 14/32 CROSS each other, so they are checked together.
  - ICAO requires runway clearances (land, take off, line up, cross, hold short) and conditional
    clearances to be read back; the controller must get a correct readback.

Assumptions (written down, to be reviewed by an ATC professional)
  - Without radar/ADS-B position data, a clearance "holds" the runway for a fixed time:
    LAND 240 s, TAKEOFF 120 s, LINEUP 300 s (or until that aircraft's take-off clearance),
    CROSS 120 s, STOPPED 600 s. A go-around releases a landing; a new runway clearance for the
    same aircraft replaces its old one.
  - A readback is expected within 10 s, and is paired with clearances up to 30 s old.
"""
import re
from sentinel_actions import analyse
from sentinel_parse import AIRLINES, AIRPORTS

STRIPS = {
    "VIDP": [("09", "27"), ("10", "28"), ("11L", "29R"), ("11R", "29L")],
    "VABB": [("09", "27"), ("14", "32")],
    "VAPO": [("10", "28")],
}
INTERSECTING = {"VABB": [("09/27", "14/32")]}
HOLD_TIME = {"LAND": 240, "TAKEOFF": 120, "LINEUP": 300, "CROSS": 120, "STOPPED": 600}
OCCUPY = {"LAND", "TAKEOFF", "LINEUP", "CROSS"}
READBACK_DUE, READBACK_WINDOW = 10, 30
MUST_READ_BACK = {"LAND", "TAKEOFF", "LINEUP", "CROSS", "HOLD_SHORT", "TAXI_HP"}


def strip_of(airport, rw):
    for a, b in STRIPS[airport]:
        if rw in (a, b):
            return f"{a}/{b}"
    return None


def related_strips(airport, strip):
    out = {strip}
    for a, b in INTERSECTING.get(airport, []):
        if strip in (a, b):
            out |= {a, b}
    return out


def _conflict_level(new, old, new_cond):
    """How bad is it to give `new` while `old` is still active on the same (or a crossing) strip?"""
    if new == "LINEUP" and old == "LAND" and new_cond:
        return None                 # "behind the landing traffic, line up" is the legal way to do this
    if new == "LINEUP" and old == "LINEUP":
        return "AMBER"              # two aircraft lined up (e.g. intersection departure) - check
    return "RED"


PHASE_OF = {"LAND": "air", "TAKEOFF": "ground", "LINEUP": "ground", "CROSS": "ground", "STOPPED": "ground"}


def _same_phase(a, b):
    return PHASE_OF.get(a) == PHASE_OF.get(b)


def _unknown(cs):
    return cs.startswith("UNIDENTIFIED")


class RunwayEngine:
    def __init__(self, airport, traffic, phases=None):
        self.airport, self.traffic, self.phases = airport, set(traffic), dict(phases or {})
        self.occ = {}               # strip -> list of {"cs","action","rw","t","until"}
        self.pending = []           # clearances waiting for a readback
        self.alerts, self.log = [], []

    # ---------------------------------------------------------------- helpers
    def _alert(self, t, level, kind, text, cs=(), rw=None):
        # callsigns keep the order given (who it is about first) - the spoken alert uses that order
        a = {"t": t, "level": level, "kind": kind, "text": text, "rw": rw,
             "callsigns": [c for c in dict.fromkeys(cs) if c]}
        self.alerts.append(a)
        return a

    def _prune(self, t):
        for s in self.occ:
            self.occ[s] = [o for o in self.occ[s] if o["until"] > t]

    def _release(self, cs, actions=None, strip=None):
        for s in self.occ:
            if strip and s != strip:
                continue
            self.occ[s] = [o for o in self.occ[s] if not (o["cs"] == cs and (actions is None or o["action"] in actions))]

    def _check_conflict(self, t, cs, action, rw, cond, hypothetical=False):
        strip = strip_of(self.airport, rw)
        out = []
        for s in related_strips(self.airport, strip):
            for o in self.occ.get(s, []):
                if o["cs"] == cs:
                    continue
                lvl = _conflict_level(action, o["action"], cond)
                if lvl and (_unknown(cs) or _unknown(o["cs"])) and _same_phase(action, o["action"]):
                    # who it is is not known, and both clearances fit ONE aircraft (e.g. two take-off clearances):
                    # it may be the same aircraft cleared twice -> possible conflict, upgraded once identified.
                    # If one needs an airborne aircraft and the other one on the ground (BOM_2024: LAND vs TAKEOFF),
                    # they CANNOT be the same aircraft, so the conflict is real now: it stays RED.
                    lvl = "AMBER"
                if lvl and cs:
                    where = strip if s == strip else f"{strip} (crosses {s})"
                    pre = f"IF {cs} DOES WHAT IT READ BACK: " if hypothetical else ""
                    out.append(self._alert(t, lvl, "RUNWAY_CONFLICT",
                                           f"{pre}RUNWAY CONFLICT on {where}: {cs} {action} {rw} while "
                                           f"{o['cs']} {o['action']} {o['rw']} (cleared {t - o['t']:.0f} s ago)",
                                           (cs, o["cs"]), rw=rw))
        return out

    def _occupy(self, t, cs, action, rw):
        strip = strip_of(self.airport, rw)
        self._release(cs)                                   # one runway clearance per aircraft at a time
        self.occ.setdefault(strip, []).append({"cs": cs, "action": action, "rw": rw, "t": t,
                                               "until": t + HOLD_TIME[action]})

    # ---------------------------------------------------------------- the one entry point
    def call(self, t, channel, text, second_text=None):
        self._prune(t)
        new = self.tick(t)
        a = analyse(text, self.airport, self.traffic, channel, self.phases, second_text)
        rec = {"t": t, "channel": channel, "text": text, "analysis": a, "alerts": new}
        if channel == "tower":
            rec["alerts"] += self._tower(t, a)
        elif channel == "pilot":
            due = any(p["cs"] in (a["callsign"], None) and not p["answered"] and t - p["t"] <= READBACK_WINDOW
                      for p in self.pending)
            if re.search(r"\bVACATED\b", a["normalized"].upper()) and a["callsign"] and not due \
                    and not any(x["action"] for x in a["instructions"]) and not a["call_actions"]:
                # "Runway vacated, IFLY 5134" (10 dB: heard as "Report vacated. IFLY 5134"): the runway is free.
                # NOT when a readback is due from this aircraft: "crossing 28, report vacated" with "crossing"
                # clipped by push-to-talk would otherwise free a runway the aircraft is about to cross.
                self._release(a["callsign"])
                rec["analysis"] = dict(a, status="REPORT")
                rec["alerts"].append(self._alert(t, "INFO", "VACATED", f"{a['callsign']} reports runway vacated", (a["callsign"],)))
            else:
                # no second-listen comparison here: A6 showed the same audio is misheard the same way
                rec["alerts"] += self._readback(t, a, None, rec)
        else:
            rec["alerts"] += self._vehicle(t, a)
        self.log.append(rec)
        return rec

    def tick(self, t):
        """Clearances whose readback is overdue."""
        out = []
        for p in self.pending:
            if not p["answered"] and not p["overdue"] and t - p["t"] > READBACK_DUE:
                p["overdue"] = True
                urgent = set(p["call_actions"]) & {"STOP", "GO_AROUND"}
                out.append(self._alert(t, "RED" if urgent else "AMBER", "NO_READBACK",
                                       f"NO READBACK from {p['cs'] or 'unknown aircraft'} for "
                                       f"{', '.join(p['call_actions'] or [f'{x} {r}' for r, x in p['ins']]) or 'an unclear clearance'}", (p["cs"],)))
        return out

    # ---------------------------------------------------------------- tower
    def _tower(self, t, a):
        cs, out = a["callsign"], []
        if a["status"] == "FLAGGED":
            out.append(self._alert(t, "AMBER", "UNCLEAR_CLEARANCE",
                                   f"Tower call not fully understood ({'; '.join(a['problems'])}) - runway picture may be incomplete", (cs,)))
        cond = any("conditional" in x for x in a["amber"])
        # an instruction the air/ground check rejected is NOT known (e.g. "cleared for takeoff" heard for
        # an airborne aircraft): keep it out of the picture rather than check readbacks against it
        bad = {p.split()[0] for p in a["problems"] if " does not fit " in p}
        ins = [(x["runway"], x["action"]) for x in a["instructions"]
               if x["valid"] and x["action"] and x["action"] not in bad]
        if not cs:
            # who it was for is not known, but SOMEONE was cleared onto that runway: it goes into the picture
            # as an unidentified aircraft (adding to the picture can only add alarms, never hide one).
            # The readback (a separate transmission) usually tells us who it was.
            ph = f"UNIDENTIFIED (cleared at t={t:.0f}s)"
            for rw, act in ins:
                if act in OCCUPY:
                    out += self._check_conflict(t, ph, act, rw, cond)
                    self._occupy(t, ph, act, rw)
            if ins or a["call_actions"]:
                self.pending.append({"t": t, "cs": None, "placeholder": ph, "ins": ins,
                                     "call_actions": list(a["call_actions"]), "cond": cond,
                                     "answered": False, "overdue": False, "unclear": True, "analysis": a})
            return out
        if "GO_AROUND" in a["call_actions"]:
            self._release(cs, {"LAND"})
        if "STOP" in a["call_actions"]:
            for s in self.occ:
                for o in self.occ[s]:
                    if o["cs"] == cs:
                        o["action"], o["until"] = "STOPPED", t + HOLD_TIME["STOPPED"]
        for rw, act in ins:
            if act in OCCUPY:
                out += self._check_conflict(t, cs, act, rw, cond)
                self._occupy(t, cs, act, rw)
            elif act in ("HOLD_SHORT", "TAXI_HP"):
                self._release(cs, {"CROSS", "LINEUP"}, strip_of(self.airport, rw))
        # "hold short, runway 29 as well": the instruction was heard, only the side of the runway was lost.
        # Keep it as a PARTIAL clearance (29L or 29R) so the readback can still be checked against it.
        rws = AIRPORTS[self.airport]["runways"]
        partial = [(x["runway"], x["action"], sorted(r for r in rws if r.rstrip("LRC") == x["runway"] and r != x["runway"]))
                   for x in a["instructions"] if not x["valid"] and x["action"] and x["runway"].isdigit()]
        partial = [p for p in partial if p[2]]
        unknown_ins = not ins and not partial and not a["call_actions"] and a["status"] == "FLAGGED" and bool(a["instructions"])
        if ins or a["call_actions"] or unknown_ins or partial:
            # unknown_ins: e.g. "hold short runway 29 as well" (side lost) - the readback can still be paired,
            # but it can never be confirmed against an instruction we did not understand
            self.pending.append({"t": t, "cs": cs, "ins": ins, "call_actions": list(a["call_actions"]),
                                 "cond": cond, "answered": False, "overdue": False, "ins_unknown": unknown_ins, "partial": partial,
                                 "unclear": a["status"] == "FLAGGED", "analysis": a})
        return out

    # ---------------------------------------------------------------- readback
    def _pick_clearance(self, t, a):
        live = [p for p in self.pending if not p["answered"] and t - p["t"] <= READBACK_WINDOW]
        if not live:
            return None, None
        if a["callsign"]:
            same = [p for p in live if p["cs"] == a["callsign"]]
            if same:
                return same[-1], None
            if len(live) == 1:
                if live[0]["cs"] is None:
                    return live[0], None
                return live[0], f"read back as {a['callsign']} (also on frequency)"
            return None, None
        heard = [(m.group(1), m.group(2)) for p in a["problems"]
                 for m in [re.match(r"callsign ([A-Z]{3})(\d+)\w* not", p)] if m]
        if heard:
            code, num = heard[0]
            match = [p for p in live if p["cs"] and p["cs"][:3] == code]
            if len(match) == 1:
                return match[0], num
        if len(live) == 1:
            return live[0], None
        return None, None

    def recheck_readback(self, rec, second_text):
        """Second listen (verbatim, NO tower context) of a readback whose callsign did not match.
        NOT USED in the pipeline: Experiment A6 (1 Nov) FAILED its rule - it fixed 1 of 15 false REDs.
        Root cause: the noise is part of the recording, so Prisma mishears the same audio the same way
        (12 of 15 second listens heard the identical wrong digits). Only a NEW transmission ("say again")
        is independent evidence. Kept, with tests, so the finding can be re-checked on human audio."""
        p = rec.get("pending")
        if not p or "callsign" not in p.get("why_kind", ""):
            return rec
        for al in rec["alerts"]:
            if al in self.alerts:
                self.alerts.remove(al)
        p["answered"] = False
        a2 = analyse(second_text, self.airport, self.traffic, rec["channel"], self.phases)
        rec["alerts"] = self._readback(rec["t"], rec["analysis"], a2, rec)
        rec["second_text"] = second_text
        return rec

    @staticmethod
    def _number_of(a, code):
        if a is None:
            return None
        if a["callsign"] and a["callsign"][:3] == code:
            return a["callsign"][3:]
        for p in a["problems"]:
            m = re.match(r"callsign ([A-Z]{3})(\d+)\w* not", p)
            if m and m.group(1) == code:
                return m.group(2)
        return None

    def _readback(self, t, a, a2=None, rec=None):
        p, heard = self._pick_clearance(t, a)
        if rec is not None:
            rec["pending"] = p
        if not p:
            return [self._alert(t, "AMBER", "UNMATCHED_READBACK",
                                "Pilot call could not be matched to a recent clearance", (a["callsign"],))] \
                + self._in_use_warnings(t, a)
        p["answered"] = True
        wrong, missing = [], []
        # --- callsign
        if p["cs"] is None:
            missing.append(f"tower's callsign was not heard; readback says {a['callsign']}, not cross-checked"
                           if a["callsign"] else "tower's callsign was not heard, and none in the readback")
        elif a["callsign"] == p["cs"]:
            pass
        elif isinstance(heard, str) and heard.startswith("read back as"):
            wrong.append(f"CALLSIGN MISMATCH: {heard}, clearance was for {p['cs']} - confirm callsign")
        elif heard:
            want = p["cs"][3:]
            code = p["cs"][:3]
            if want.startswith(heard) and 1 <= len(want) - len(heard) <= 2:
                missing.append(f"callsign incomplete ({code}{heard}_)")
            else:
                n2 = self._number_of(a2, code)
                if n2 == want:
                    # listen 2 positively heard the CLEARED number: the two hearings disagree, so it may be
                    # Prisma's slip - ask, don't accuse. (Listen 2 hearing nothing, or a third number, is not
                    # evidence of anything: RED stays.)
                    missing.append(f"callsign unclear: listen 1 heard {code}{heard}, listen 2 heard {p['cs']} - confirm callsign")
                else:
                    note = "" if a2 is None else (" (heard the same in both listens)" if n2 == heard
                                                  else f" (listen 2: {code + n2 if n2 else 'no number'})")
                    wrong.append(f"CALLSIGN MISMATCH in readback: heard {code}{heard}, cleared {p['cs']}{note} - confirm callsign")
                p["why_kind"] = "callsign"
        else:
            missing.append("callsign not heard")
        # --- runway + instruction
        rb = {x["runway"]: x for x in a["instructions"]}
        rb_valid = {r for r, x in rb.items() if x["valid"]}
        for digits, act, cands in p.get("partial", []):
            got = [r for r in rb_valid if r in cands]
            if len(got) == 1:
                # the readback says WHICH runway (29R). That cannot be cross-checked (the tower's side was lost),
                # but it locates the clearance so its safety can be checked.
                p["ins"] = p["ins"] + [(got[0], act)]
                missing.append(f"tower's runway side not heard ({digits}?); readback says {got[0]}, not cross-checked")
            else:
                missing.append(f"tower's runway side not heard ({digits}?) and the readback does not settle it")
        p["partial"] = []
        for rw, act in p["ins"]:
            if rw in rb_valid:
                got = rb[rw]["action"]
                if got is None:
                    if act in MUST_READ_BACK:
                        missing.append(f"instruction for runway {rw} not heard")
                elif got != act:
                    wrong.append(f"INSTRUCTION MISMATCH in readback: {got} {rw}, cleared {act} {rw}")
            else:
                others = sorted(rb_valid - {r for r, _ in p["ins"]})
                if others:
                    wrong.append(f"RUNWAY MISMATCH in readback: {others[0]}, cleared {act} {rw}")
                else:
                    missing.append(f"runway {rw} not read back clearly")
        if p.get("ins_unknown"):
            missing.append("the tower's instruction was not understood, so this readback cannot be checked")
        for c in p["call_actions"]:
            if c not in a["call_actions"]:
                missing.append(f"{c} not confirmed")
        if p["cond"] and not any("conditional" in x for x in a["amber"]):
            missing.append("condition ('behind traffic') not read back")
        out = []
        who = p["cs"] or a["callsign"] or "unknown aircraft"
        if wrong and p["unclear"]:
            # the reference itself was not heard cleanly: say so, don't claim a pilot error
            out.append(self._alert(t, "AMBER", "READBACK_DIFFERS_UNCLEAR",
                                   f"{who}: readback differs from what was heard of the tower call ("
                                   + "; ".join(wrong + missing) + ") - tower call was unclear, confirm", (p["cs"],)))
            p["verdict"], p["why"] = "INCOMPLETE", wrong + missing
            return out
        if wrong:
            out.append(self._alert(t, "RED", "READBACK_MISMATCH", f"{who}: " + "; ".join(wrong + missing), (p["cs"],),
                                   rw=p["ins"][0][0] if p["ins"] else None))
            # what if the pilot does what he read back?
            for x in a["instructions"]:
                if x["valid"] and x["action"] in OCCUPY and (x["runway"], x["action"]) not in p["ins"]:
                    out += self._check_conflict(t, p["cs"], x["action"], x["runway"], False, hypothetical=True)
        elif missing:
            urgent = any(c in m for m in missing for c in ("STOP", "GO_AROUND"))
            # A HOLD SHORT that is not confirmed, on a runway someone else is using right now, is the classic
            # incursion set-up (ICAO: hold-short instructions must be read back). Not a guess: it is "not confirmed",
            # exactly like STOP. Consequence decides the level.
            hold_rw, other = None, None
            for rw, act in p["ins"]:
                if act == "HOLD_SHORT" and f"instruction for runway {rw} not heard" in missing:
                    users = [o for s2 in related_strips(self.airport, strip_of(self.airport, rw))
                             for o in self.occ.get(s2, []) if o["cs"] != p["cs"]]
                    if users:
                        hold_rw, other = rw, users[-1]["cs"]
                        missing.insert(0, f"HOLD SHORT not confirmed - runway {rw} in use: {users[-1]['cs']} "
                                          f"{users[-1]['action']} {users[-1]['rw']}")
            out.append(self._alert(t, "RED" if urgent or hold_rw else "AMBER", "READBACK_INCOMPLETE",
                                   f"{who}: readback incomplete - " + "; ".join(missing) + " - confirm", (p["cs"], other),
                                   rw=hold_rw))
        p["verdict"] = "MISMATCH" if wrong else ("INCOMPLETE" if missing else "MATCH")
        p["why"] = wrong + missing
        # the tower's callsign was lost but the readback says who it was: name the aircraft in the picture
        # and re-check it (only when nothing in the readback contradicts the clearance)
        if p.get("placeholder") and a["callsign"] and not wrong:
            for st in list(self.occ):
                for o in self.occ[st]:
                    if o["cs"] == p["placeholder"]:
                        self._release(a["callsign"])
                        o["cs"] = a["callsign"]
                        out += self._check_conflict(t, a["callsign"], o["action"], o["rw"], p["cond"])
                        twin = [x for x in a["amber"] if x.startswith("similar callsign on frequency")]
                        if twin:
                            # the aircraft was named ONLY by its own readback: a look-alike could have answered
                            out.append(self._alert(t, "AMBER", "NAMED_BY_READBACK_ONLY",
                                                   f"{a['callsign']} named only by its readback ({twin[0]}) - confirm who is cleared",
                                                   (a["callsign"],)))
            p["placeholder"] = None
        out += self._in_use_warnings(t, a)
        return out

    def _in_use_warnings(self, t, a):
        """A call that names a runway someone else holds, with no instruction heard for it: say so."""
        out, who = [], a["callsign"] or "unidentified station"
        for x in a["instructions"]:
            if not x["valid"] or x["action"] is not None:
                continue
            strip = strip_of(self.airport, x["runway"])
            for st in related_strips(self.airport, strip):
                for o in self.occ.get(st, []):
                    shown = any(al["level"] == "RED" and t - al["t"] <= 60
                                and {a["callsign"], o["cs"]} <= set(al["callsigns"]) for al in self.alerts)
                    if o["cs"] != a["callsign"] and not shown:
                        out.append(self._alert(t, "AMBER", "RUNWAY_IN_USE_UNCLEAR",
                                               f"{who} named runway {x['runway']} (instruction not heard) - in use: "
                                               f"{o['cs']} {o['action']} {o['rw']} (cleared {t - o['t']:.0f} s ago) - confirm",
                                               (a["callsign"], o["cs"])))
        return out

    # ---------------------------------------------------------------- vehicles
    def _vehicle(self, t, a):
        out = self._in_use_warnings(t, a)
        for x in a["instructions"]:
            if not x["valid"]:
                continue
            strip = strip_of(self.airport, x["runway"])
            users = [o for s in related_strips(self.airport, strip) for o in self.occ.get(s, [])]
            if x["action"] in ("REQ_CROSS", "REQ_ENTER") and users:
                u = users[-1]
                out.append(self._alert(t, "AMBER", "VEHICLE_REQUEST_OCCUPIED",
                                       f"{a['callsign'] or 'vehicle'} asks for runway {x['runway']} - in use: "
                                       f"{u['cs']} {u['action']} {u['rw']} (cleared {t - u['t']:.0f} s ago)",
                                       (a["callsign"], u["cs"])))
            if x["action"] == "REPORT_BIRDS":
                if users:
                    for u in users:
                        out.append(self._alert(t, "RED", "BIRDS_ON_ACTIVE_RUNWAY",
                                               f"Birds reported on runway {x['runway']} by {a['callsign'] or 'vehicle'} - "
                                               f"{u['cs']} {u['action']} {u['rw']}", (a["callsign"], u["cs"]), rw=x["runway"]))
                else:
                    out.append(self._alert(t, "AMBER", "BIRDS_REPORTED",
                                           f"Birds reported on runway {x['runway']} by {a['callsign'] or 'vehicle'}", (a["callsign"],)))
        return out

    # ---------------------------------------------------------------- surveillance hook (optional)
    def observed_on_runway(self, t, cs, rw):
        """A position report (ADS-B surface / ground radar) that `cs` is ON runway `rw`.
        Voice alone cannot see this: at Haneda (Jan 2024) the Coast Guard aircraft read back
        "taxi to holding point C5" correctly and then entered the runway. With a position feed,
        a runway entry without a matching clearance is an incursion."""
        self._prune(t)
        strip = strip_of(self.airport, rw)
        mine = [o for o in self.occ.get(strip, []) if o["cs"] == cs]
        out = []
        if not mine:
            out.append(self._alert(t, "RED", "INCURSION",
                                   f"RUNWAY INCURSION: {cs} seen on runway {rw} without a clearance for it", (cs,), rw=rw))
            out += self._check_conflict(t, cs, "LINEUP", rw, False)
        return out