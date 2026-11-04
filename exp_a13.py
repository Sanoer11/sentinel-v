"""
Experiment A13 - give every "seen in only 1 voice" problem a fair test: the 6 Timbre v3.0 dev voices
(the locked-exam voices are NOT used) say exactly the lines that break, clean / 10 dB / 5 dB.

  R1 "Runway two niner right, cleared for takeoff, Vistara seven two five."   (Runway -> Taxiway / One way / Airway?)
  R2 "Runway two seven, cleared to land, Air India six five seven."
  R3 "Crossing runway two niner right, IFLY five one three four."             (Crossing -> Sing / Thing / I think?)
  R4 "Holding short runway two niner right, IFLY five one three four."
  R5 "Runway vacated, IFLY five one three four."                              (vacated -> "vacate it"?)
  T1 "IFLY five one three four, hold short runway two niner right."           (29 -> 39?)
  T2 "Akasa Air one one two three, runway two niner left, cleared for takeoff."

RULES - FIXED NOW, before any result:
  W. Each "Runway" sound-alike (taxiway, one way, airway) goes ON (sentinel_actions.RUNWAY_SOUNDALIKES_ON) only if
     W1 it starts a call (before the runway number) in >= 2 DIFFERENT voices in A13,
     W2 re-scoring every saved tower/pilot transcript (dev, dev2, step1) + A13 with it on vs off: 0 worse, 0 new WRONG,
        >= 1 better,
     W3 replaying every saved scenario run with it on: 0 runs worse, 0 extra false RED in normal traffic.
  V. "vacate" stem (sentinel_state.VACATE_STEM) goes ON only if
     V1 a vacate form without the word "vacated" is heard in >= 2 voices,
     V2 the R5 sequence (land 29L, vacated, takeoff 29L) gives fewer false REDs with it, and never more,
     V3 in every saved pilot transcript, the stem matches only lines whose spoken text really says "vacat...",
     V4 replays: 0 runs worse, 0 extra false RED.
  D. Misheard runway digit (sentinel_state.RW_BAD_LOCATE, ON since the 4 Nov free checks): stays ON unless, on the
     T1 lines, it makes any sequence worse than with it off. How often it helps is reported.
  C. "Crossing" clipped: REPORT ONLY (no mapping: a clipped "Holding" sounds the same, guessing would be unsafe).

Run:   python exp_a13.py results/dev_20261031_000600.json results/dev2_20261031_004232.json results/step1_20261031_013014.json
Cost:  42 TTS + about 140 STT  ~ Rs 9   (finished clips are kept; re-run the same command if it stops)
"""
import os
import re
import sys
import glob
import json
import hashlib
from collections import defaultdict

import sentinel_actions
import sentinel_state
from scoring import judge_full, truth_of
from exp_a9 import V3_DEV, RANK

CONDS = ["clean", "10", "5"]
PROGRESS = "results/exp_a13_progress.json"
VIDP = ["VTI725", "VTI926", "AIC2817", "IGO5134", "AKJ1123"]
VABB = ["AIC657", "IGO6053"]

LINES = {
    "R1": ("pilot", "VIDP", VIDP, "VTI725", [["29R", "TAKEOFF"]], "ground",
           "Runway two niner right, cleared for takeoff, Vistara seven two five."),
    "R2": ("pilot", "VABB", VABB, "AIC657", [["27", "LAND"]], "air",
           "Runway two seven, cleared to land, Air India six five seven."),
    "R3": ("pilot", "VIDP", VIDP, "IGO5134", [["29R", "CROSS"]], "ground",
           "Crossing runway two niner right, IFLY five one three four."),
    "R4": ("pilot", "VIDP", VIDP, "IGO5134", [["29R", "HOLD_SHORT"]], "ground",
           "Holding short runway two niner right, IFLY five one three four."),
    "R5": ("pilot", "VIDP", VIDP, "IGO5134", None, "air", "Runway vacated, IFLY five one three four."),
    "T1": ("tower", "VIDP", VIDP, "IGO5134", [["29R", "HOLD_SHORT"]], "ground",
           "IFLY five one three four, hold short runway two niner right."),
    "T2": ("tower", "VIDP", VIDP, "AKJ1123", [["29L", "TAKEOFF"]], "ground",
           "Akasa Air one one two three, runway two niner left, cleared for takeoff."),
}
SOUNDALIKES = sorted(sentinel_actions.RUNWAY_SOUNDALIKES)
NUMW = r"(?:\d|zero|one|two|three|tree|four|five|fife|six|seven|eight|nine|niner)"


def items():
    out = []
    for v in V3_DEV:
        for k, (ch, ap, tr, cs, ins, ph, text) in LINES.items():
            out.append(dict(id=f"a13_{k}_{v}", line=k, voice=v, channel=ch, airport=ap, traffic=tr, action="a13",
                            text=text, phase={cs: ph}, traps=[],
                            truth={"callsign": cs, "instructions": ins or [], "call_actions": [], "conditional": False}))
    return out


def listen(todo):
    from gnani_client import tts, stt
    import soundfile as sf
    from radio_sim import radio
    from sentinel_pipeline import hear
    rows = json.load(open(PROGRESS, encoding="utf-8")) if os.path.exists(PROGRESS) else []
    done = {(r["id"], r["cond"]) for r in rows}
    for it in todo:
        clean = f"audio_eval/a13/{it['id']}.wav"
        if not tts(it["text"], it["voice"], "timbre-v3.0", "en-IN", clean):
            print(f"  TTS failed: {it['id']}"); continue
        for c in CONDS:
            if (it["id"], c) in done:
                continue
            path = clean if c == "clean" else clean.replace(".wav", f"_snr{c}.wav")
            if not os.path.exists(path):
                x, sr = sf.read(clean)
                sf.write(path, radio(x, sr, int(c), seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)),
                         8000, subtype="PCM_16")
            h = hear(path, it["channel"], it["airport"], it["traffic"], stt)
            rows.append({"id": it["id"], "cond": c, "heard": h["text"], "heard2": h["text2"]})
            json.dump(rows, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {it['id']:<16} {c:<5} {h['text']}")
    return rows


def opener(text):
    """The first two words of a call: 'Taxiway 2, niner right...' -> 'taxiway 2'."""
    return " ".join(re.findall(r"[A-Za-z0-9]+", (text or "").lower())[:2])


def old_rows(files):
    out = []
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if res.get("testset") == "locked":
            raise SystemExit("Refusing: that is the LOCKED exam.")
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        its = {it["id"]: it for it in ts["items"]}
        out += [(its[r["id"]], r["heard"], r.get("heard2"), f"{res['testset']}:{r['id']}:{r['cond']}")
                for r in res["results"] if its[r["id"]]["channel"] != "airside"]
    return out


def rescore(pool, word):
    better, worse, new_wrong = [], [], []
    for it, t, t2, tag in pool:
        if not it["truth"]["instructions"] and it.get("line") == "R5":
            continue
        sentinel_actions.RUNWAY_SOUNDALIKES_ON = set()
        o1 = judge_full(it, t, t2)[0]
        sentinel_actions.RUNWAY_SOUNDALIKES_ON = {word}
        o2 = judge_full(it, t, t2)[0]
        sentinel_actions.RUNWAY_SOUNDALIKES_ON = set()
        if RANK[o2] > RANK[o1]:
            better.append((tag, o1, o2, t))
        elif RANK[o2] < RANK[o1]:
            worse.append((tag, o1, o2, t))
            new_wrong += [tag] if o2 == "WRONG" else []
    return better, worse, new_wrong


def replays(setter):
    """Every saved scenario run, flag off vs on. Returns (worse, extra false RED, better)."""
    import exp_a12
    runs = [r for f in sorted(glob.glob("results/scenarios_2026*.json")) if "dry" not in f
            for r in json.load(open(f, encoding="utf-8"))]
    order = {"PASS": 2, "LATE": 1, "FAIL": 0}
    worse = better = fr_off = fr_on = 0
    for r in runs:
        setter(False); v1, f1 = exp_a12.replay(r)
        setter(True);  v2, f2 = exp_a12.replay(r)
        setter(False)
        worse += order[v2] < order[v1]; better += order[v2] > order[v1]
        fr_off += f1; fr_on += f2
    return worse, fr_on - fr_off, better, len(runs)


def vacate_sequence(text):
    e = sentinel_state.RunwayEngine("VIDP", VIDP, {"IGO5134": "air", "AKJ1123": "ground"})
    e.call(0, "tower", "IFLY 5134, runway 29 left, cleared to land.")
    e.call(4, "pilot", "Cleared to land runway 29 left, IFLY 5134.")
    e.call(100, "pilot", text)
    r = e.call(110, "tower", "Akasa Air 1123, runway 29 left, cleared for takeoff.")
    return any(a["level"] == "RED" for a in r["alerts"])


def hold_sequence(tower_text, tower_text2):
    e = sentinel_state.RunwayEngine("VIDP", VIDP, {"AIC2817": "ground", "IGO5134": "ground"})
    e.call(0, "tower", "Air India 2817, runway 29 right, cleared for takeoff.")
    e.call(4, "pilot", "Runway 29 right, cleared for takeoff, Air India 2817.")
    e.call(15, "tower", tower_text, tower_text2)
    r = e.call(19, "pilot", "Crossing runway 29 right, IFLY 5134.")
    kinds = {(a["level"], a["kind"]) for a in r["alerts"]}
    return 2 if ("RED", "READBACK_MISMATCH") in kinds and ("RED", "RUNWAY_CONFLICT") in kinds \
        else 1 if any(a["level"] == "RED" for a in r["alerts"]) else 0


def main():
    files = sys.argv[1:]
    bad = [f for f in files if not os.path.isfile(f)]
    if not files or bad:
        raise SystemExit(f"Give the old result files (dev, dev2, step1). Not a file: {bad}  (nothing run, nothing paid)")
    todo = items()
    by = {it["id"]: it for it in todo}
    broken = [it["id"] for it in todo if it["line"] != "R5" and judge_full(it, it["text"])[0] != "OK"]
    broken += [it["id"] for it in todo if it["line"] == "R5" and vacate_sequence(it["text"])]
    if broken:
        raise SystemExit(f"Scripted lines that do not score right as perfect text (fix the script first): {broken}")
    print(f"{len(todo)} lines x 3 conditions: {len(todo)} TTS + about 140 STT, about Rs 9.")
    if input("Continue? [y/N] ").strip().lower() != "y":
        return
    os.makedirs("results", exist_ok=True)
    rows = listen(todo)
    a13 = [(by[r["id"]], r["heard"], r["heard2"], f"a13:{r['id']}:{r['cond']}") for r in rows]
    olds = old_rows(files)

    print("\n================ W: 'Runway' sound-alikes at the start of a call ================")
    openers = defaultdict(set)
    for it, t, _, _ in a13:
        if it["line"] in ("R1", "R2"):
            openers[opener(t)].add(it["voice"])
    print("  R1/R2 first words heard (said 'Runway'):",
          ", ".join(f"'{w}' x{len(v)} voices" for w, v in sorted(openers.items(), key=lambda x: -len(x[1]))))
    for w in SOUNDALIKES:
        pat = re.compile(r"^\W*" + sentinel_actions.RUNWAY_SOUNDALIKES[w] + r"\b", re.IGNORECASE)
        voices = sorted({it["voice"] for it, t, _, _ in a13 if pat.search(t or "")})
        better, worse, new_wrong = rescore(olds + a13, w)
        def setter(on, w=w):
            sentinel_actions.RUNWAY_SOUNDALIKES_ON = {w} if on else set()
        r_worse, r_fr, r_better, n = replays(setter)
        ok = len(voices) >= 2 and better and not worse and not new_wrong and not r_worse and r_fr <= 0
        print(f"\n  '{w}': voices {len(voices)} {voices} | re-score better {len(better)} worse {len(worse)} new WRONG "
              f"{len(new_wrong)} | {n} replays: better {r_better} worse {r_worse} extra false RED {r_fr}")
        for tag, o1, o2, t in better[:4] + worse:
            print(f"     {'+' if RANK[o2] > RANK[o1] else '!!'} {tag:<30} {o1} -> {o2}   {t}")
        print(f"  VERDICT '{w}':", "PASS - add to RUNWAY_SOUNDALIKES_ON" if ok else "FAIL - stays off")

    print("\n================ V: 'vacated' ================")
    r5 = [(it, t) for it, t, _, _ in a13 if it["line"] == "R5"]
    stem_only = sorted({it["voice"] for it, t in r5 if re.search(r"vacat", t or "", re.I) and not re.search(r"vacated", t or "", re.I)})
    lost = [(it["voice"], t) for it, t in r5 if not re.search(r"vacat", t or "", re.I)]
    sentinel_state.VACATE_STEM = False; red_off = sum(vacate_sequence(t) for _, t in r5)
    sentinel_state.VACATE_STEM = True;  red_on = sum(vacate_sequence(t) for _, t in r5)
    sentinel_state.VACATE_STEM = False
    stray = [tag for it, t, _, tag in olds if it["channel"] == "pilot" and re.search(r"\bvacat(e|ing)\b", t or "", re.I)
             and not re.search(r"vacat", it["text"], re.I)]
    def vset(on):
        sentinel_state.VACATE_STEM = on
    v_worse, v_fr, v_better, n = replays(vset)
    print(f"  {len(r5)} 'Runway vacated' clips: heard without 'vacated' but with 'vacat..': voices {stem_only} | "
          f"no 'vacat' at all: {len(lost)}")
    for v, t in lost:
        print(f"     lost ({v}): {t}")
    print(f"  false RED in the land/vacated/takeoff sequence: stem off {red_off}, stem on {red_on}")
    print(f"  saved pilot lines where the stem matches but nobody said 'vacat..': {len(stray)} {stray[:5]}")
    print(f"  {n} replays: better {v_better} worse {v_worse} extra false RED {v_fr}")
    v_ok = len(stem_only) >= 2 and red_on < red_off and not stray and not v_worse and v_fr <= 0
    print("  VERDICT vacate stem:", "PASS - set VACATE_STEM = True" if v_ok else "FAIL - stays off")

    print("\n================ D: misheard runway digit (T1) ================")
    t1 = [(it, r["heard"], r["heard2"], r["cond"]) for r in rows for it in [by[r["id"]]] if it["line"] == "T1"]
    d_worse = d_better = impossible = 0
    for it, t, t2, c in t1:
        rws = [x["runway"] for x in sentinel_actions.analyse(t, "VIDP", VIDP, "tower", None, t2)["instructions"]]
        if any(r not in ("29R",) for r in rws):
            impossible += 1
        sentinel_state.RW_BAD_LOCATE = False; s0 = hold_sequence(t, t2)
        sentinel_state.RW_BAD_LOCATE = True;  s1 = hold_sequence(t, t2)
        d_worse += s1 < s0; d_better += s1 > s0
        if s1 != s0 or s1 < 2:
            print(f"     {it['voice']:<8} {c:<5} {'+' if s1 > s0 else '!!' if s1 < s0 else ' '} off {s0} -> on {s1}  {t}")
    print(f"  {len(t1)} tower clips | runway heard as something else in {impossible} | D better {d_better} worse {d_worse}"
          "   (2 = mismatch + conflict RED, 1 = another RED, 0 = no RED)")
    print("  VERDICT D:", "stays ON" if not d_worse else "FAIL - set RW_BAD_LOCATE = False")

    print("\n================ C: 'Crossing' clipped (report only) ================")
    r3 = [(it["voice"], c, t) for (it, t, _, tag) in a13 for c in [tag.split(":")[-1]] if it["line"] == "R3"]
    gone = [(v, c, t) for v, c, t in r3 if not re.search(r"cross", t or "", re.I)]
    print(f"  {len(r3)} 'Crossing runway...' clips: the word 'cross' lost in {len(gone)}")
    for v, c, t in gone:
        print(f"     {v:<8} {c:<5} {t}")
    print("\nPaste the whole output.")


if __name__ == "__main__":
    main()
