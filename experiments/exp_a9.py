"""
Experiment A9 - fresh voices for the two things that rested on ONE voice:
  Part A  the bird hint (पक्षी) - tested on 1 Marathi voice (Zahira), and its "only when listen 1 didn't
          understand" split was found AFTER the A8 run
  Part B  five mishearings each seen in only 1 voice:
            "Casa Air" (Akasa Air)   "following" (Follow Me)   "Force" (Bird Chaser four)
            "writer" (right at)      "379 or 2" (three seven niner two)

New audio: the 6 Timbre v3.0 dev voices speak Marathi, Hinglish and English lines they never spoke before.
The locked-exam voices (v2.5 set + Ishaan) are NOT used. Clean, 10 dB and 5 dB radio.

RULES - FIXED NOW, before any result. Nothing is changed in the code by this script; it prints the verdict.

Part A - the hint stays ON only if all hold (else: HINT_MODE = "off" in sentinel_pipeline.py):
  A1. listen 1 lost the bird report in at least one clip (else: "NOT TESTED" - the hint stays, still a limit)
  A2. the hint brought back >= 1/3 of those
  A3. 0 false bird reports (a line with no birds that ends up showing birds)
  A4. 0 lines where the hint was USED and the result got worse than listen 1 alone

Part B - a word mapping goes into sentinel_parse.FIXES only if all hold:
  B1. the variant shows up in >= 2 DIFFERENT voices here (new evidence, not the old voice)
  B2. applied to EVERY transcript (all A9 lines + every old result file given on the command line),
      0 lines get worse and 0 new WRONG
  B3. >= 1 line gets better
  Ranking used for better/worse: OK 3 > AMBER 2 > FLAG 1 > WRONG 0 (the same judge_full as every run).

Run:   python experiments/exp_a9.py results/dev_*.json results/dev2_*.json results/step1_*.json
       (the old files are only re-scored as text: no new Prisma calls for them; the locked set is refused)
       python experiments/exp_a9.py --rescore results/exp_a9_<time>.json results/dev_*.json ...   (no API calls)
Cost:  about 54 TTS + 290 STT  ~ Rs 17 (printed before it starts)
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
import datetime

from scoring import judge_full

V3_DEV = ["Avinash", "Riyaa", "Harshad", "Prakash", "Devansh", "Shubham"]
CONDS = ["clean", "10", "5"]
PROGRESS = "results/exp_a9_progress.json"
RANK = {"OK": 3, "AMBER": 2, "FLAG": 1, "WRONG": 0}

DEV = {"0": "ज़ीरो", "1": "वन", "2": "टू", "3": "थ्री", "4": "फोर", "5": "फाइव", "6": "सिक्स", "7": "सेवन",
       "8": "एट", "9": "नाइन"}
EN = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
      "8": "eight", "9": "niner"}
BOM_RW = ["09", "27", "14", "32"]

# The candidate mappings (applied to the raw transcript, before the parser). OFF in the real code.
CANDIDATES = {
    "casa":      (r"\b(?:a\s*)?casa\s+air\b", "Akasa Air"),
    "following": (r"\b(?:our\s+)?following\b(?=[\s,]*(?:\d|zero|one|two|three|four|five)\b)", "Follow Me"),
    "force":     (r"\b(chaser|chester|follow\s*me)\s+force\b", r"\1 four"),
    "writer":    (r"\b(?:a\s+)?writer\b", "right"),
    "or":        (r"(\d)\s+or\s+(\d)", r"\1\2"),
}


def say(num, table):
    return " ".join(table[c] for c in num)


def items():
    rng = random.Random(909)
    out = []
    for v in V3_DEV:
        # ---- Part A: Marathi vehicle lines (2 bird reports + 2 crossing requests per voice) ----
        for k in range(4):
            n, rw = str(rng.randint(1, 5)), rng.choice(BOM_RW)
            birds = k < 2
            text = (f"टॉवर, बर्ड चेसर {DEV[n]}, रनवे {say(rw, DEV)} वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय."
                    if birds else f"टॉवर, बर्ड चेसर {DEV[n]}, मला रनवे {say(rw, DEV)} ओलांडायचा आहे, परवानगी द्या.")
            other = str(rng.choice([x for x in range(1, 6) if str(x) != n]))
            out.append(dict(id=f"a9A_{v}_{k}", part="A", channel="airside", airport="VABB", action="vehicle",
                            voice=v, tts_lang="mr-IN", text=text, variant=None,
                            traffic=sorted({"BIRDCHASER" + n, "BIRDCHASER" + other, "AIC657"}),
                            truth={"callsign": "BIRDCHASER" + n, "conditional": False, "call_actions": [],
                                   "instructions": [[rw, "REPORT_BIRDS" if birds else "REQ_CROSS"]]}, phase=None))
        # ---- Part B: one line per variant per voice ----
        d = str(rng.randint(100, 999)) + str(rng.randint(0, 9))
        out.append(dict(id=f"a9B_casa_{v}", part="B", variant="casa", channel="tower", airport="VIDP",
                        action="land", voice=v, tts_lang="en-IN", text=f"Akasa Air {say(d, EN)}, runway two niner left, cleared to land.",
                        traffic=sorted({"AKJ" + d, "AIC2817", "IGO5134"}), phase={"AKJ" + d: "air"},
                        truth={"callsign": "AKJ" + d, "conditional": False, "call_actions": [],
                               "instructions": [["29L", "LAND"]]}))
        d = str(rng.randint(1000, 9999))
        out.append(dict(id=f"a9B_writer_{v}", part="B", variant="writer", channel="tower", airport="VIDP",
                        action="cross", voice=v, tts_lang="en-IN",
                        text=f"IFLY {say(d, EN)}, cross runway two niner right at Bravo, report vacated.",
                        traffic=sorted({"IGO" + d, "AIC2817"}), phase={"IGO" + d: "ground"},
                        truth={"callsign": "IGO" + d, "conditional": False, "call_actions": [],
                               "instructions": [["29R", "CROSS"]]}))
        d = str(rng.randint(10, 99)) + "9" + str(rng.randint(1, 8))
        out.append(dict(id=f"a9B_or_{v}", part="B", variant="or", channel="pilot", airport="VABB",
                        action="lineup", voice=v, tts_lang="en-IN",
                        text=f"Line up and wait runway two seven, Air India {say(d, EN)}.",
                        traffic=sorted({"AIC" + d, "IGO5134"}), phase={"AIC" + d: "ground"},
                        truth={"callsign": "AIC" + d, "conditional": False, "call_actions": [],
                               "instructions": [["27", "LINEUP"]]}))
        n, rw = str(rng.randint(1, 5)), rng.choice(["29R", "29L", "11R", "11L"])
        rw_said = say(rw[:2], {**EN, "9": "nine"}) + (" right" if rw[2] == "R" else " left")
        out.append(dict(id=f"a9B_following_{v}", part="B", variant="following", channel="airside", airport="VIDP",
                        action="vehicle", voice=v, tts_lang="en-IN",
                        text=f"Tower, Follow Me {EN[n] if n != '9' else 'nine'}, runway {rw_said} cross karna hai, Bravo pe hold kar raha hoon.",
                        traffic=sorted({"FOLLOWME" + n, "AIC2817"}), phase=None,
                        truth={"callsign": "FOLLOWME" + n, "conditional": False, "call_actions": [],
                               "instructions": [[rw, "REQ_CROSS"]]}))
        rw = rng.choice(BOM_RW)
        out.append(dict(id=f"a9B_force_{v}", part="B", variant="force", channel="airside", airport="VABB",
                        action="vehicle", voice=v, tts_lang="mr-IN",
                        text=f"टॉवर, बर्ड चेसर फोर, मला रनवे {say(rw, DEV)} ओलांडायचा आहे, परवानगी द्या.",
                        traffic=sorted({"BIRDCHASER4", "BIRDCHASER2", "AIC657"}), phase=None,
                        truth={"callsign": "BIRDCHASER4", "conditional": False, "call_actions": [],
                               "instructions": [[rw, "REQ_CROSS"]]}))
    return out


def fixed(text, names):
    if text is None:
        return None
    for nm in names:
        pat, rep = CANDIDATES[nm]
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)
    return text


def grade(it, text, text2, hinted, names=()):
    o, r = judge_full(it, fixed(text, names), fixed(text2, names), hinted)
    birds = any(x["action"] == "REPORT_BIRDS" for x in r["instructions"])
    return o, birds


def listen(todo):
    from gnani_client import tts, stt
    import soundfile as sf
    from radio_sim import radio
    from sentinel_pipeline import hear
    # 4 Nov: a network timeout killed the run after 3 paid calls and kept nothing. Every finished clip is
    # now written to PROGRESS at once; a re-run skips what is already there (same audio -> same text, A6/A7).
    rows = json.load(open(PROGRESS, encoding="utf-8")) if os.path.exists(PROGRESS) else []
    done = {(r["id"], r.get("cond")) for r in rows}
    if done:
        print(f"  resuming: {len(rows)} clips already heard, kept from {PROGRESS}")

    def save():
        os.makedirs("results", exist_ok=True)
        json.dump(rows, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for it in todo:
        if all((it["id"], c) in done for c in CONDS) or (it["id"], None) in done:
            continue
        clean = f"audio_eval/a9/{it['id']}.wav"
        if not tts(it["text"], it["voice"], "timbre-v3.0", it["tts_lang"], clean):
            print(f"  TTS failed for {it['id']} ({it['voice']}, {it['tts_lang']}) - skipped, counted below")
            rows.append({"id": it["id"], "tts_failed": True}); save()
            continue
        for c in CONDS:
            if (it["id"], c) in done:
                continue
            path = clean
            if c != "clean":
                path = clean.replace(".wav", f"_snr{c}.wav")
                if not os.path.exists(path):
                    x, sr = sf.read(clean)
                    sf.write(path, radio(x, sr, int(c), seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)),
                             8000, subtype="PCM_16")
            h = hear(path, it["channel"], it["airport"], it["traffic"], stt, speculative=False, hint_mode="v1")   # A9 tested v1
            rows.append({"id": it["id"], "cond": c, "first": h["first"], "hint_text": h.get("hint_text"),
                         "text": h["text"], "text2": h["text2"], "hinted": h["hinted"]})
            save()
            print(f"  {it['id']:<22} {c:<5} {h['text']}" + ("   [hint used]" if h["hinted"] else ""))
    return rows


def old_rows(files):
    """Every transcript from earlier runs, re-scored as text only (for rule B2)."""
    out = []
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if not isinstance(res, dict) or "testset" not in res:
            print(f"  {f}: not a run_eval result file - skipped"); continue
        if res["testset"] == "locked":
            raise SystemExit("Refusing: that is the LOCKED exam. It is never opened before the final run.")
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        its = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            if r["id"] in its and not str(r.get("heard", "")).startswith("<error"):
                out.append((its[r["id"]], r["heard"], r.get("heard2"), r.get("hinted", False), f"{res['testset']}:{r['id']}:{r['cond']}"))
    return out


def main():
    args = sys.argv[1:]
    # fail BEFORE paying: zsh passed "#" and "~₹17" from my pasted comment as file names (4 Nov)
    missing = [f for f in (args[2:] if args[:1] == ["--rescore"] else args) if not os.path.isfile(f)]
    if missing or (args[:1] == ["--rescore"] and not os.path.isfile(args[1])):
        raise SystemExit(f"Not a file: {missing or args[1:2]}  (nothing was run, nothing paid)")
    todo = items()
    by_id = {it["id"]: it for it in todo}
    # sanity: every scripted line must score OK as perfect text, or the experiment itself is broken
    broken = [(it["id"], grade(it, it["text"], None, False)[0]) for it in todo]
    broken = [b for b in broken if b[0] and b[1] != "OK"]
    if broken:
        raise SystemExit(f"Scripted lines that do not score OK as perfect text (fix the script first): {broken}")
    if args and args[0] == "--rescore":
        rows = json.load(open(args[1], encoding="utf-8"))["rows"]
        args = args[2:]
    else:
        n_stt = sum(1 for it in todo for _ in CONDS) + sum(1 for it in todo if it["channel"] == "airside") * len(CONDS)
        print(f"{len(todo)} new lines x {len(CONDS)} conditions: {len(todo)} TTS + about {n_stt + 20} STT, "
              f"about Rs {0.05 * (len(todo) + n_stt + 20):.0f}.")
        if input("Continue? [y/N] ").strip().lower() != "y":
            return
        rows = listen(todo)
        os.makedirs("results", exist_ok=True)
        path = f"results/exp_a9_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
        json.dump({"rows": rows}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"Saved {path}")
    failed_tts = [r["id"] for r in rows if r.get("tts_failed")]
    rows = [r for r in rows if not r.get("tts_failed")]

    # ================= Part A =================
    print("\n================ PART A: bird hint on 6 new Marathi voices ================")
    lost = back = false_birds = worse = 0
    for r in [r for r in rows if by_id[r["id"]]["part"] == "A"]:
        it = by_id[r["id"]]
        is_birds = it["truth"]["instructions"][0][1] == "REPORT_BIRDS"
        o1, b1 = grade(it, r["first"], None if r["hinted"] else r["text2"], False)
        o2, b2 = grade(it, r["text"], r["text2"], r["hinted"])
        tag = ""
        if is_birds and not b1:
            lost += 1
            ok = r["hinted"] and b2 and o2 != "WRONG"
            back += ok
            tag = "BIRDS BACK (hint)" if ok else "birds lost"
        if not is_birds and b2:
            false_birds += 1; tag = "!! FALSE BIRDS"
        if r["hinted"] and RANK[o2] < RANK[o1]:
            worse += 1; tag += " !! HINT MADE IT WORSE"
        if tag or o2 != "OK":
            print(f"  {r['id']:<18} {r['cond']:<5} {o1} -> {o2}  {tag}\n     listen 1 : {r['first']}"
                  + (f"\n     hint     : {r['hint_text']}" if r.get("hint_text") else ""))
    voices_lost = len({by_id[r['id']]['voice'] for r in rows if by_id[r['id']]['part'] == 'A'})
    print(f"\nA: bird report lost by listen 1 in {lost} clips | brought back by the hint {back} | "
          f"FALSE birds {false_birds} | hint made a line worse {worse}   ({voices_lost} voices)")
    if not lost:
        print("A VERDICT: NOT TESTED - listen 1 never lost the bird word on these voices. The hint stays; still a limit.")
    elif back * 3 >= lost and false_birds == 0 and worse == 0:
        print("A VERDICT: PASS - the hint stays on (now shown on new voices, not just Zahira).")
    else:
        print("A VERDICT: FAIL - set HINT_MODE = 'off' in sentinel_pipeline.py.")

    # ================= Part B =================
    print("\n================ PART B: the five one-voice mishearings ================")
    every = [(by_id[r["id"]], r["text"], r["text2"], r["hinted"], f"a9:{r['id']}:{r['cond']}") for r in rows]
    olds = old_rows(args)
    every += olds
    print(f"(rule B2 checks {len(every)} transcripts: {len(rows)} new + {len(olds)} from {len(args)} old file(s))")
    for nm, (pat, _) in CANDIDATES.items():
        seen_voices = sorted({by_id[r["id"]]["voice"] for r in rows
                              if re.search(pat, (r["first"] or "") + " " + (r["text2"] or ""), re.IGNORECASE)})
        better, worse_l, new_wrong = [], [], []
        for it, t, t2, hinted, tag in every:
            if not re.search(pat, (t or "") + " " + (t2 or ""), re.IGNORECASE):
                continue
            o1, _ = grade(it, t, t2, hinted)
            o2, _ = grade(it, t, t2, hinted, (nm,))
            if RANK[o2] > RANK[o1]:
                better.append((tag, o1, o2, t))
            elif RANK[o2] < RANK[o1]:
                worse_l.append((tag, o1, o2, t))
                if o2 == "WRONG":
                    new_wrong.append(tag)
        ok = len(seen_voices) >= 2 and not worse_l and not new_wrong and better
        print(f"\n  '{nm}': seen in {len(seen_voices)} voice(s) {seen_voices} | better {len(better)} | worse {len(worse_l)} "
              f"| new WRONG {len(new_wrong)}  ->  "
              + ("PASS: add to FIXES" if ok else "NOT SEEN on new voices: not added" if not seen_voices else "FAIL: not added"))
        for tag, o1, o2, t in better[:4] + worse_l:
            print(f"     {'+' if RANK[o2] > RANK[o1] else '!!'} {tag:<34} {o1} -> {o2}   {t}")
    if failed_tts:
        print(f"\nTTS failed for {len(failed_tts)} lines (voice cannot speak that language?): {failed_tts}")
    print("\nPaste the whole output.")


if __name__ == "__main__":
    main()
