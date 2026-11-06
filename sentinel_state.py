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
from sentinel_actions import analyse, _hits, STRONG
from sentinel_parse import AIRLINES, AIRPORTS

STRIPS = {
    "VIDP": [("09", "27"), ("10", "28"), ("11L", "29R"), ("11R", "29L")],
    "VABB": [("09", "27"), ("14", "32")],
    "VAPO": [("10", "28")],
}
INTERSECTING = {"VABB": [("09/27", "14/32")]}
HOLD_TIME = {"LAND": 240, "TAKEOFF": 120, "LINEUP": 300, "CROSS": 120, "STOPPED": 600}
OCCUPY = {"LAND", "TAKEOFF", "LINEUP", "CROSS"}
# DEL_2023 10 dB (4 Nov): a clearance whose runway (or side) was lost, LOCATED by its readback, is kept and put
# in the runway picture. Checked free on every saved transcript and scenario run by exp_a12.py.
# A12 (4 Nov): readback check 0 missed / false RED 15 -> 15; 272 scenario replays 0 worse -> ON.
# Extended the same night (HOLD_AS_CROSS noise 5): the readback may locate it whatever instruction it reads back,
# if its runway fits the heard digits. Same free checks re-run; then NEW noise 10-14 (rule in exp_a12.py).
LOCATE_FROM_READBACK = True
# An UNIDENTIFIED clearance whose heard number fragments clearly cannot be the other aircraft ("9826" vs VTI725) is
# not "maybe the same aircraft cleared twice": its conflict stays RED (DEL_2023 noise 8). Free checks: exp_a12.py.
EXCLUDE_BY_NUMBER = True
# "Runway vacated" heard as "Can we vacate it" (NORMAL_DEL noise 17, one voice): the stem form is OFF until A13.
# A13: 0 voices said a "vacate" form without "vacated" -> FAIL -> OFF. 3 of 18 "Runway vacated" were lost completely
# ("Did I fly 5134?", "Cleared for takeoff, IFLY 5134" x2 voices): no wording rule can recover those; the RED then
# says "no 'runway vacated' heard from ..." so the controller can check the runway with one look.
VACATE_STEM = False
# misheard runway digit ("runway 39" for 29) located by a readback one digit away: free checks passed 4 Nov,
# not yet seen on fresh noise -> A13 Part D measures it.
# A13 Part D (fresh voices): 1 of 18 tower clips had "runway 39" -> with it RED mismatch + conflict, without it no RED;
# 0 worse -> stays ON.
RW_BAD_LOCATE = True
# Experiment A14 (7 Nov), Fix U: "runway 290, right, cleared for takeoff" - the runway was lost (glued digits) and
# the readback lost it too ("Taxiway 2, niner right"), so the take-off never entered the picture and the later
# crossing of 29R looked safe (DEL_2023 at 10 dB: 6 of 20 missed, all this way). The glued digits still say which
# runways it COULD be (290 + right -> 29R). Those go into the picture as "maybe": any conflict with them is AMBER
# "POSSIBLE RUNWAY CONFLICT", never RED. Off until exp_a14.py passes its rules.
MAYBE_RUNWAY = True
VACATE_RE = r"\bVACATED\b"
VACATE_STEM_RE = r"\bVACAT(ED|E|ING)\b"
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


def _heard_numbers(normalized):
    """Number fragments heard in a call that are NOT runway numbers ("Tara, 9826, cross runway 298R" -> {"9826"})."""
    from sentinel_parse import NOT_CALLSIGN_BEFORE
    # only where a callsign stands (ICAO: first words of a tower call, last words of a readback), never after
    # runway / wind / QNH ... - the same positions anchor_callsign uses
    toks = re.findall(r"[A-Z]+|\d+[A-Z]?", normalized.upper())
    edge = set(range(min(3, len(toks)))) | set(range(max(0, len(toks) - 3), len(toks)))
    return {toks[i] for i in sorted(edge) if toks[i].isdigit() and len(toks[i]) <= 5
            and not (i > 0 and (toks[i - 1] in NOT_CALLSIGN_BEFORE or toks[i - 1] == "RUNWAY"))}


def _could_be(nums, cs):
    """Could an UNIDENTIFIED aircraft, of which only these number fragments were heard, be `cs`?
    DEL_2023 10 dB noise 8 (4 Nov): crossing clearance for "Tara, 9826" (really VTI926), readback "Vistara 9 ...":
    neither fragment can be VTI725's "725", so the crossing is NOT VTI725 cleared twice -> the conflict is real.
    Kept deliberately loose (only a clear mismatch excludes): a fragment that contains, or is contained in, the
    flight number, is one edit from it, or starts with the same digit -> "could be" (e.g. "15725", "7725", "775").
    Nothing heard -> could be."""
    from sentinel_parse import edit_distance
    num = cs[3:] if cs[:3] in AIRLINES.values() else None
    if not nums or not num:
        return True
    return any(n in num or num in n or edit_distance(n, num) <= 1 or n[0] == num[0] for n in nums)


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

    def _check_conflict(self, t, cs, action, rw, cond, hypothetical=False, nums=None, maybe=None):
        strip = strip_of(self.airport, rw)
        out = []
        for s in related_strips(self.airport, strip):
            for o in self.occ.get(s, []):
                if o["cs"] == cs:
                    continue
                lvl = _conflict_level(action, o["action"], cond)
                maybe_same = (_unknown(cs) and _could_be(nums, o["cs"])) or (_unknown(o["cs"]) and _could_be(o.get("nums"), cs))
                if (_unknown(cs) and _unknown(o["cs"])) or (not EXCLUDE_BY_NUMBER and (_unknown(cs) or _unknown(o["cs"]))):
                    maybe_same = True
                if lvl and maybe_same and _same_phase(action, o["action"]):
                    # who it is is not known, and both clearances fit ONE aircraft (e.g. two take-off clearances):
                    # it may be the same aircraft cleared twice -> possible conflict, upgraded once identified.
                    # If one needs an airborne aircraft and the other one on the ground (BOM_2024: LAND vs TAKEOFF),
                    # they CANNOT be the same aircraft, so the conflict is real now: it stays RED.
                    lvl = "AMBER"
                heard_as = maybe or o.get("maybe")
                if lvl and cs and heard_as:
                    # one side of this conflict is only a "maybe" runway (its number was heard glued): AMBER, never RED
                    who_maybe, rw_maybe = (cs, rw) if maybe else (o["cs"], o["rw"])
                    out.append(self._alert(t, "AMBER", "RUNWAY_CONFLICT_POSSIBLE",
                                           f"POSSIBLE RUNWAY CONFLICT on {strip}: {cs} {action} {rw} while {o['cs']} {o['action']} "
                                           f"{o['rw']} - {who_maybe}'s runway was heard as '{heard_as}', could be {rw_maybe} - confirm",
                                           (cs, o["cs"]), rw=rw))
                    continue
                if lvl and cs:
                    where = strip if s == strip else f"{strip} (crosses {s})"
                    pre = f"IF {cs} DOES WHAT IT READ BACK: " if hypothetical else ""
                    out.append(self._alert(t, lvl, "RUNWAY_CONFLICT",
                                           f"{pre}RUNWAY CONFLICT on {where}: {cs} {action} {rw} while "
                                           f"{o['cs']} {o['action']} {o['rw']} (cleared {t - o['t']:.0f} s ago"
                                           # NORMAL_DEL noise 17 (5 Nov): "Runway vacated" heard as "Can we vacate it"
                                           # -> the landing aircraft is still in the picture. Say WHY, so the
                                           # controller can check it in one look (the level does not change).
                                           + (f"; no 'runway vacated' heard from {o['cs']}" if o["action"] == "LAND"
                                              and t - o["t"] > 60 else "") + ")",
                                           (cs, o["cs"]), rw=rw))
        return out

    def _occupy(self, t, cs, action, rw, nums=None):
        strip = strip_of(self.airport, rw)
        self._release(cs)                                   # one runway clearance per aircraft at a time
        self.occ.setdefault(strip, []).append({"cs": cs, "action": action, "rw": rw, "t": t,
                                               "until": t + HOLD_TIME[action], "nums": set(nums or ())})

    # ---------------------------------------------------------------- the one entry point
    def call(self, t, channel, text, second_text=None, hinted=False):
        self._prune(t)
        new = self.tick(t)
        a = analyse(text, self.airport, self.traffic, channel, self.phases, second_text)
        if hinted:
            # this transcript came from the hazard-vocabulary listen (sentinel_pipeline): never shown as plain green
            a = dict(a, amber=a["amber"] + ["heard with hazard-word hint (vehicle channel)"],
                     status="FLAGGED" if a["status"] == "FLAGGED" else "PROBABLE")
        rec = {"t": t, "channel": channel, "text": text, "analysis": a, "alerts": new}
        if channel == "tower":
            rec["alerts"] += self._tower(t, a)
        elif channel == "pilot":
            due = any(p["cs"] in (a["callsign"], None) and not p["answered"] and t - p["t"] <= READBACK_WINDOW
                      for p in self.pending)
            if re.search(VACATE_STEM_RE if VACATE_STEM else VACATE_RE, a["normalized"].upper()) and a["callsign"] and not due \
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
            got = self._vehicle(t, a)
            for al in got:
                if hinted:
                    al["text"] += " [heard with hazard-word hint]"
            rec["alerts"] += got
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
        # "ARF 725, runway 290, right. Cleared for takeoff." - the instruction was heard, the runway number was
        # lost (glued 290). Keep the instruction; the readback may say WHICH runway (as for a lost side, below).
        rw_unknown = []
        if LOCATE_FROM_READBACK and not ins and not a["call_actions"] and not any(x["valid"] for x in a["instructions"]):
            acts = {act for _, act, _, _ in _hits(a["normalized"].upper(), STRONG, "strong") if act in MUST_READ_BACK}
            rw_unknown = sorted(acts) if len(acts) == 1 else []
        # glued digits that were heard ("runway 291"): the readback's runway must start with them (29R fits 291)
        glued = re.search(r"\bRUNWAY\s+(\d{3,})", a["normalized"].upper())
        rw_digits = glued.group(1) if glued and rw_unknown else None
        # a runway number that does not exist here ("hold short runway 39" at Delhi, said 29): one digit misheard.
        # The readback's runway must be ONE digit away from it (29R vs 39) to locate the clearance.
        rw_bad = sorted({x["runway"].rstrip("LRC") for x in a["instructions"] if not x["valid"]}) \
            if rw_unknown and RW_BAD_LOCATE else []
        if MAYBE_RUNWAY and rw_digits:
            gm = re.search(r"\bRUNWAY\s+\d{3,}\s*(R|L|C|RIGHT|LEFT|CENTRE|CENTER)\b", a["normalized"].upper())
            side = gm.group(1)[0] if gm else None
            cands = sorted(r for r in AIRPORTS[self.airport]["runways"]
                           if rw_digits.startswith(r.rstrip("LRC")) and (side is None or r.endswith(side)))
            who = cs or f"UNIDENTIFIED (cleared at t={t:.0f}s)"
            nums = None if cs else _heard_numbers(a["normalized"])
            if 1 <= len(cands) <= 2:
                for act in rw_unknown:
                    if act not in OCCUPY:
                        continue
                    for rw in cands:
                        out += self._check_conflict(t, who, act, rw, cond, nums=nums, maybe=f"{rw_digits}{side or ''}")
                        self.occ.setdefault(strip_of(self.airport, rw), []).append(
                            {"cs": who, "action": act, "rw": rw, "t": t, "until": t + HOLD_TIME[act],
                             "nums": set(nums or ()), "maybe": f"{rw_digits}{side or ''}"})
        if not cs:
            # who it was for is not known, but SOMEONE was cleared onto that runway: it goes into the picture
            # as an unidentified aircraft (adding to the picture can only add alarms, never hide one).
            # The readback (a separate transmission) usually tells us who it was.
            ph = f"UNIDENTIFIED (cleared at t={t:.0f}s)"
            for rw, act in ins:
                if act in OCCUPY:
                    out += self._check_conflict(t, ph, act, rw, cond, nums=_heard_numbers(a["normalized"]))
                    self._occupy(t, ph, act, rw, nums=_heard_numbers(a["normalized"]))
            if ins or a["call_actions"] or rw_unknown:
                self.pending.append({"t": t, "cs": None, "placeholder": ph, "ins": ins, "rw_unknown": rw_unknown,
                                     "nums": _heard_numbers(a["normalized"]),
                                     "rw_digits": rw_digits,
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
        if partial:
            rw_unknown, rw_bad = [], []
        # (rw_unknown: the instruction WAS understood, only its runway was not - so it is not "unknown_ins")
        unknown_ins = not ins and not partial and not rw_unknown and not a["call_actions"] and a["status"] == "FLAGGED" \
            and bool(a["instructions"])
        if ins or a["call_actions"] or unknown_ins or partial or rw_unknown:
            # unknown_ins: e.g. "hold short runway 29 as well" (side lost) - the readback can still be paired,
            # but it can never be confirmed against an instruction we did not understand
            self.pending.append({"t": t, "cs": cs, "ins": ins, "call_actions": list(a["call_actions"]),
                                 "cond": cond, "answered": False, "overdue": False, "ins_unknown": unknown_ins, "partial": partial,
                                 "rw_unknown": rw_unknown, "rw_digits": rw_digits, "rw_bad": rw_bad,
                                 # unclear ONLY because the runway number was lost or misheard: callsign + instruction heard
                                 "runway_only": bool(rw_unknown) and cs is not None
                                                and all(pr == "no runway heard" or any(
                                                    pr == f"runway {b}{sd} does not exist at {AIRPORTS[self.airport]['name']}"
                                                    for b in rw_bad for sd in ("", "L", "R", "C")) for pr in a["problems"]),
                                 "unclear": a["status"] == "FLAGGED", "analysis": a,
                                 # unclear ONLY because the runway side was lost ("29 as well"): callsign and
                                 # instruction were heard. If the readback settles the side, an INSTRUCTION
                                 # mismatch is a real one (hold short vs crossing does not depend on the side).
                                 "side_only": bool(partial) and cs is not None and a["status"] == "FLAGGED"
                                              and all(any(pr == f"runway {d} does not exist at {AIRPORTS[self.airport]['name']}"
                                                          for d, _, _ in partial) for pr in a["problems"])})
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
        side_settled = bool(p.get("partial"))
        located = []
        rw_settled = bool(p.get("rw_unknown"))
        for act in p.get("rw_unknown", []):
            # HOLD_AS_CROSS 10 dB noise 5 (4 Nov): tower "hold short runway 291", readback "Crossing runway 29 right".
            # The readback names ONE runway that fits the heard digits: that locates the clearance whatever
            # instruction the pilot read back - comparing the instructions is the point of the check.
            from sentinel_parse import edit_distance
            got = [r for r in rb_valid
                   if (not p.get("rw_digits") or p["rw_digits"].startswith(r.rstrip("LRC")))
                   and (not p.get("rw_bad") or any(edit_distance(r.rstrip("LRC"), b) <= 1 for b in p["rw_bad"]))]
            rw_settled = rw_settled and len(got) == 1
            if len(got) == 1:
                p["ins"] = p["ins"] + [(got[0], act)]
                located.append((got[0], act))
                heard_as = f"heard as {'/'.join(p['rw_bad'])} (no such runway)" if p.get("rw_bad") else "not heard"
                missing.append(f"tower's runway {heard_as}; readback says {got[0]}, not cross-checked")
            else:
                missing.append("tower's runway not heard and the readback does not settle it")
        p["rw_unknown"] = []
        for digits, act, cands in p.get("partial", []):
            got = [r for r in rb_valid if r in cands]
            side_settled = side_settled and len(got) == 1
            if len(got) == 1:
                # the readback says WHICH runway (29R). That cannot be cross-checked (the tower's side was lost),
                # but it locates the clearance so its safety can be checked.
                p["ins"] = p["ins"] + [(got[0], act)]
                located.append((got[0], act))
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
        # HOLD_AS_CROSS at 10 dB (4 Nov, 2 of 5 noise recordings): tower "hold short runway 29 as well" (side
        # lost), readback "crossing runway 29 right" -> was only AMBER "tower call unclear". The unclear part
        # (side) is settled by the readback and has nothing to do with HOLD SHORT vs CROSSING: that stays RED.
        clear_enough = ((p.get("side_only") and side_settled) or (p.get("runway_only") and rw_settled)) \
            and all(w.startswith("INSTRUCTION MISMATCH") for w in wrong)
        if wrong and p["unclear"] and not clear_enough:
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
        if not wrong and LOCATE_FROM_READBACK:
            # a clearance located only by its readback (tower's runway or side lost) goes into the picture too:
            # the pilot will act on what he read back. Adding to the picture can only add alarms, never hide one.
            who_cs = p["cs"] or a["callsign"] or p.get("placeholder")
            if located:
                # the readback settled the runway: the "maybe" runways of this clearance are no longer needed
                # (A14 first run: the maybe entry, renamed later, released the located one and turned a RED into AMBER)
                gone = {p["cs"], p.get("placeholder"), a["callsign"]} - {None}
                for st in self.occ:
                    self.occ[st] = [o for o in self.occ[st] if not (o.get("maybe") and o["cs"] in gone)]
            for rw, act in located:
                if act in OCCUPY and who_cs:
                    nums = (p.get("nums") or set()) | _heard_numbers(a["normalized"]) if _unknown(who_cs) else None
                    out += self._check_conflict(t, who_cs, act, rw, p["cond"], nums=nums)
                    self._occupy(p["t"], who_cs, act, rw, nums=nums)        # cleared when the TOWER spoke, not at the readback
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
