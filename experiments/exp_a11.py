"""
Experiment A11 - the English "birds" cue, and a fair re-run of A10.

Why: A10 failed hint v2 on rule A3 (1 false bird). Double-check showed that false bird came from LISTEN 1,
not from the hint: "4 birds is a 5 runway 27" = a garbled "Bird Chaser 5", and the parser's English "BIRDS"
cue fired on the station's own name. Rule A3 counted it against the hint, which did not cause it.
The real fault is the cue. Our tests never had an English bird report, so the cue was never tested at all.

  Part E  NEW English vehicle lines (bird reports + Bird Chaser lines with no birds), 6 v3.0 dev voices,
          clean / 10 / 5 dB. Compares the old cue with the strict cue (sentinel_actions.BIRDS_EN_STRICT).
  Part S  every saved vehicle transcript (dev, dev2, step1, A9, A10) re-scored, old cue vs strict. No API.
  Part R  A10 Part A re-heard (same cached audio, no TTS) with the strict cue + hint v2, A10's rules UNCHANGED.
          Needed because with the strict cue, listen 1 of that clip no longer "understands" the call, so the
          hint is now asked there - its answer was never recorded.

RULES - FIXED NOW, before any result:
  Strict cue -> BIRDS_EN_STRICT = True only if ALL hold on Part E + Part S:
    S1. 0 true bird reports that the old cue shows and the strict cue misses
    S2. 0 false birds with the strict cue (the A10 clip it came from must be among them, but proves nothing alone)
    S3. the strict cue shows the bird report in >= 1/2 of the English bird clips where listen 1 kept the word
        "bird" (else the English cue does not work and that is reported, not hidden)
  Part R -> HINT_MODE = "v2" only if Strict PASSED and A10's rules all hold on the re-run:
    A1 lost >= 3 | A2 back >= 1/3 | A3 0 false birds | A4 0 lines made worse by the hint
  If Strict fails, Part R is printed for information only and changes nothing.

Run:   python experiments/exp_a11.py results/dev_*.json results/dev2_*.json results/step1_*.json
Cost:  30 TTS + about 140 STT  ~ Rs 9   (finished clips are kept; re-run the same command if it stops)
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import re
import json
import random
import hashlib

import sentinel_actions
import sentinel_pipeline
from exp_a9 import V3_DEV, RANK, grade, items as a9_items
from exp_a10 import items as a10_items
from scoring import truth_of

CONDS = ["clean", "10", "5"]
PROGRESS = "results/exp_a11_progress.json"
EN = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "0": "zero", "7": "seven", "9": "nine"}
BOM_RW = ["09", "27", "14", "32"]


def say(rw):
    return " ".join(EN[c] for c in rw)


def e_items():
    rng = random.Random(1111)
    out = []
    for v in V3_DEV:
        for k in range(5):
            n, rw = str(rng.randint(1, 5)), rng.choice(BOM_RW)
            other = str(rng.choice([x for x in range(1, 6) if str(x) != n]))
            text, act = [
                (f"Tower, Bird Chaser {EN[n]}, birds on runway {say(rw)}, we are dispersing them.", "REPORT_BIRDS"),
                (f"Tower, Bird Chaser {EN[n]}, heavy bird activity on runway {say(rw)}.", "REPORT_BIRDS"),
                (f"Tower, Bird Chaser {EN[n]}, runway {say(rw)}, a flock of birds near the centreline.", "REPORT_BIRDS"),
                (f"Tower, Bird Chaser {EN[n]}, request to cross runway {say(rw)} at Bravo.", "REQ_CROSS"),
                (f"Tower, Bird Chaser {EN[n]}, request to enter runway {say(rw)} for FOD check.", "REQ_ENTER"),
            ][k]
            out.append(dict(id=f"a11_{v}_{k}", channel="airside", airport="VABB", action="vehicle", voice=v,
                            tts_lang="en-IN", text=text, phase=None,
                            traffic=sorted({"BIRDCHASER" + n, "BIRDCHASER" + other, "AIC657"}),
                            truth={"callsign": "BIRDCHASER" + n, "conditional": False, "call_actions": [],
                                   "instructions": [[rw, act]]}))
    return out


def shows_birds(text, it, strict):
    sentinel_actions.BIRDS_EN_STRICT = strict
    try:
        a = sentinel_actions.analyse(text, it["airport"], it["traffic"], "airside")
        return any(x["action"] == "REPORT_BIRDS" for x in a["instructions"])
    finally:
        sentinel_actions.BIRDS_EN_STRICT = False


def listen(todo, folder, mode_tag, hint_mode, strict, tts_lang_of):
    from gnani_client import tts, stt
    import soundfile as sf
    from radio_sim import radio
    from sentinel_pipeline import hear
    rows = json.load(open(PROGRESS, encoding="utf-8")) if os.path.exists(PROGRESS) else []
    done = {(r["part"], r["id"], r["cond"]) for r in rows}

    def save():
        json.dump(rows, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    conds = CONDS if mode_tag == "E" else ["10", "5"]
    for it in todo:
        clean = f"audio_eval/{folder}/{it['id']}.wav"
        if not os.path.exists(clean) and not tts(it["text"], it["voice"], "timbre-v3.0", tts_lang_of(it), clean):
            print(f"  TTS failed: {it['id']}"); continue
        for c in conds:
            if (mode_tag, it["id"], c) in done:
                continue
            path = clean if c == "clean" else clean.replace(".wav", f"_snr{c}.wav")
            if not os.path.exists(path):
                x, sr = sf.read(clean)
                sf.write(path, radio(x, sr, int(c), seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)),
                         8000, subtype="PCM_16")
            sentinel_actions.BIRDS_EN_STRICT = strict
            try:
                h = hear(path, "airside", it["airport"], it["traffic"], stt, hint_mode=hint_mode)
            finally:
                sentinel_actions.BIRDS_EN_STRICT = False
            rows.append({"part": mode_tag, "id": it["id"], "cond": c, "first": h["first"], "hint_text": h.get("hint_text"),
                         "text": h["text"], "text2": h["text2"], "hinted": h["hinted"]})
            save()
            print(f"  {mode_tag} {it['id']:<16} {c:<5} {h['text']}" + ("   [hint used]" if h["hinted"] else ""))
    return [r for r in rows if r["part"] == mode_tag]


def saved_transcripts(files):
    out = []
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if res.get("testset") == "locked":
            raise SystemExit("Refusing: that is the LOCKED exam.")
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        its = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            it = its[r["id"]]
            if it["channel"] == "airside":
                out.append((f"{res['testset']}:{r['id']}:{r['cond']}", it, truth_of(it)[0][0][1], r["heard"]))
    for name, mk, prog in (("a9", a9_items, "results/exp_a9_progress.json"), ("a10", a10_items, "results/exp_a10_progress.json")):
        if not os.path.exists(prog):
            print(f"  (missing {prog} - skipped)"); continue
        by = {it["id"]: it for it in mk()}
        for r in json.load(open(prog, encoding="utf-8")):
            if r.get("tts_failed") or by[r["id"]]["channel"] != "airside":
                continue
            it = by[r["id"]]
            for t in {r["first"], r["text"]}:
                out.append((f"{name}:{r['id']}:{r['cond']}", it, it["truth"]["instructions"][0][1], t))
    return out


def main():
    files = sys.argv[1:]
    bad = [f for f in files if not os.path.isfile(f)]
    if not files or bad:
        raise SystemExit(f"Give the old result files (dev, dev2, step1). Not a file: {bad}  (nothing run, nothing paid)")
    E = e_items()
    sentinel_actions.BIRDS_EN_STRICT = True          # "bird activity" exists only in the strict cue
    try:
        broken = [it["id"] for it in E if grade(it, it["text"], None, False)[0] != "OK"]
    finally:
        sentinel_actions.BIRDS_EN_STRICT = False
    broken += [it["id"] for it in E
               if shows_birds(it["text"], it, True) != (it["truth"]["instructions"][0][1] == "REPORT_BIRDS")]
    if broken:
        raise SystemExit(f"Scripted lines that do not score right as perfect text (fix the script first): {broken}")
    print(f"Part E: {len(E)} new English lines x 3 + Part R: 24 A10 clips x 2 (cached audio). About Rs 9.")
    if input("Continue? [y/N] ").strip().lower() != "y":
        return
    os.makedirs("results", exist_ok=True)
    rows_e = listen(E, "a11", "E", "off", False, lambda it: "en-IN")

    # ---------------- Part E + S: the cue ----------------
    print("\n================ PART E + S: English 'birds' cue, old vs strict ================")
    by_e = {it["id"]: it for it in E}
    pool = [(f"a11:{r['id']}:{r['cond']}", by_e[r["id"]], by_e[r["id"]]["truth"]["instructions"][0][1], r["first"])
            for r in rows_e] + saved_transcripts(files)
    s1 = s2 = gained = 0
    en_kept = en_shown = 0
    for tag, it, act, text in pool:
        old, new = shows_birds(text, it, False), shows_birds(text, it, True)
        is_birds = act == "REPORT_BIRDS"
        if is_birds and old and not new:
            s1 += 1; print(f"  !! MISSED by strict  {tag:<28} {text}")
        if not is_birds and new:
            s2 += 1; print(f"  !! FALSE bird strict {tag:<28} {text}")
        if is_birds and new and not old:
            gained += 1
        if not is_birds and old and not new:
            print(f"  +  false bird removed {tag:<28} {text}")
        if tag.startswith("a11:") and is_birds and re.search(r"\bbirds?\b", text, re.I):
            en_kept += 1; en_shown += new
    print(f"\nS: {len(pool)} transcripts | true birds lost by strict {s1} | false birds with strict {s2} | "
          f"English bird clips that kept the word: shown {en_shown}/{en_kept} | true birds only strict sees ('bird activity') {gained}")
    strict_ok = s1 == 0 and s2 == 0 and en_kept and en_shown * 2 >= en_kept
    print("STRICT VERDICT:", "PASS - set BIRDS_EN_STRICT = True in sentinel_actions.py." if strict_ok
          else "FAIL - stays off." + ("" if en_kept else " (no English bird clip kept the word: cue untestable here)"))

    # ---------------- Part R: A10 re-run ----------------
    A10 = a10_items()
    rows_r = listen(A10, "a10", "R", "v2", True, lambda it: "mr-IN")
    by = {it["id"]: it for it in A10}
    print("\n================ PART R: A10 re-run, strict cue + hint v2, A10 rules unchanged ================")
    lost = back = false_birds = worse = 0
    sentinel_actions.BIRDS_EN_STRICT = True
    try:
        for r in rows_r:
            it = by[r["id"]]
            is_birds = it["truth"]["instructions"][0][1] == "REPORT_BIRDS"
            o1, b1 = grade(it, r["first"], None if r["hinted"] else r["text2"], False)
            o2, b2 = grade(it, r["text"], r["text2"], r["hinted"])
            tag = ""
            if is_birds and not b1:
                lost += 1
                ok = r["hinted"] and b2 and o2 != "WRONG"
                back += ok
                tag = "BIRDS BACK" if ok else "birds lost"
            if not is_birds and b2:
                false_birds += 1; tag = "!! FALSE BIRDS" + (" (from the hint)" if r["hinted"] else " (listen 1)")
            if r["hinted"] and RANK[o2] < RANK[o1]:
                worse += 1; tag += " !! WORSE"
            if tag:
                print(f"  {r['id']:<16} {r['cond']:<3} {o1} -> {o2}  {tag}\n     listen 1 : {r['first']}"
                      + (f"\n     hint     : {r['hint_text']}" if r.get("hint_text") else ""))
    finally:
        sentinel_actions.BIRDS_EN_STRICT = False
    print(f"\nR: lost by listen 1 {lost} | back with v2 {back} | FALSE birds {false_birds} | worse {worse}")
    a_ok = lost >= 3 and back * 3 >= lost and false_birds == 0 and worse == 0
    if not strict_ok:
        print("R VERDICT: for information only (strict cue failed) - HINT_MODE stays 'off'.")
    else:
        print("R VERDICT:", "PASS - set HINT_MODE = 'v2' in sentinel_pipeline.py." if a_ok else "FAIL - HINT_MODE stays 'off'.")
    print("\nPaste the whole output.")


if __name__ == "__main__":
    main()
