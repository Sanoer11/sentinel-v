"""
Experiment A10 - two fixes that were found AFTER a run, so they need fresh evidence before going live.

  Part A  hint v2 ("the hint may add the bird word, never remove the vehicle listen 1 heard").
          Seen on the A9 clips (7/11 birds back, 0 worse) - but designed after seeing them, so A9 is NOT its test.
          Test here: NEW Marathi sentences, NEW numbers, NEW noise, the same 6 v3.0 dev voices.
  Part G  Fix G accepts a second listen that heard NO callsign (found on 1 clip: DEL_2023 10 dB noise 1).
          Test: re-score every saved transcript with and without it. No API calls.

RULES - FIXED NOW, before any result:
  Part A -> HINT_MODE = "v2" only if ALL hold, else it stays "off":
    A1. listen 1 lost the bird report in >= 3 clips (fewer = too little to judge: stays off)
    A2. v2 brings back >= 1/3 of those
    A3. 0 false bird reports (a line with no birds that ends up showing birds)
    A4. 0 lines where v2 USED the hint and the result got worse than listen 1 alone
  Part G -> FIXG_SILENT_CALLSIGN = True only if ALL hold:
    G1. >= 1 transcript gets better (DEL_2023 noise 1 itself does not count: it is where the idea came from)
    G2. 0 transcripts get worse, 0 new WRONG
  Ranking: OK 3 > AMBER 2 > FLAG 1 > WRONG 0 (judge_full, the same as every run).

Run:   python experiments/exp_a10.py results/dev_*.json results/dev2_*.json results/step1_*.json
       (re-run the same command if it stops: finished clips are kept in results/exp_a10_progress.json)
Cost:  24 TTS + about 90 STT  ~ Rs 6 (Part G is free)
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
import random
import hashlib

import sentinel_parse
from exp_a9 import DEV, say, BOM_RW, V3_DEV, RANK, grade
from scoring import judge_full

CONDS = ["10", "5"]
PROGRESS = "results/exp_a10_progress.json"


def items():
    rng = random.Random(1010)                      # A9 used 909: new numbers, new runways
    out = []
    for v in V3_DEV:
        for k in range(4):
            n, rw = str(rng.randint(1, 5)), rng.choice(BOM_RW)
            other = str(rng.choice([x for x in range(1, 6) if str(x) != n]))
            r = say(rw, DEV)
            # new wording (A9: "...वर पक्षी आहेत, मी टॅक्सीवे चार्लीजवळ थांबलोय" / "मला रनवे ... ओलांडायचा आहे")
            text, act = [
                (f"टॉवर, बर्ड चेसर {DEV[n]}, रनवे {r} वर खूप पक्षी दिसत आहेत, आम्ही त्यांना हाकलत आहोत.", "REPORT_BIRDS"),
                (f"टॉवर, बर्ड चेसर {DEV[n]}, रनवे {r} च्या मध्यभागी पक्षी आहेत, सावध रहा.", "REPORT_BIRDS"),
                (f"टॉवर, बर्ड चेसर {DEV[n]}, रनवे {r} ओलांडू का? ब्राव्हो वर थांबलो आहे.", "REQ_CROSS"),
                (f"टॉवर, बर्ड चेसर {DEV[n]}, रनवे {r} वर एफओडी तपासायला जायचं आहे, परवानगी द्या.", "REQ_ENTER"),
            ][k]
            out.append(dict(id=f"a10_{v}_{k}", channel="airside", airport="VABB", action="vehicle", voice=v,
                            tts_lang="mr-IN", text=text, phase=None,
                            traffic=sorted({"BIRDCHASER" + n, "BIRDCHASER" + other, "AIC657"}),
                            truth={"callsign": "BIRDCHASER" + n, "conditional": False, "call_actions": [],
                                   "instructions": [[rw, act]]}))
    return out


def part_a(todo):
    from gnani_client import tts, stt
    import soundfile as sf
    from radio_sim import radio
    from sentinel_pipeline import hear
    rows = json.load(open(PROGRESS, encoding="utf-8")) if os.path.exists(PROGRESS) else []
    done = {(r["id"], r.get("cond")) for r in rows}

    def save():
        json.dump(rows, open(PROGRESS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for it in todo:
        clean = f"audio_eval/a10/{it['id']}.wav"
        if all((it["id"], c) in done for c in CONDS) or (it["id"], None) in done:
            continue
        if not tts(it["text"], it["voice"], "timbre-v3.0", "mr-IN", clean):
            rows.append({"id": it["id"], "tts_failed": True}); save(); continue
        for c in CONDS:
            if (it["id"], c) in done:
                continue
            path = clean.replace(".wav", f"_snr{c}.wav")
            if not os.path.exists(path):
                x, sr = sf.read(clean)
                sf.write(path, radio(x, sr, int(c), seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)),
                         8000, subtype="PCM_16")
            h = hear(path, "airside", it["airport"], it["traffic"], stt, hint_mode="v2")
            rows.append({"id": it["id"], "cond": c, "first": h["first"], "hint_text": h.get("hint_text"),
                         "hint_rejected": h.get("hint_rejected", False),
                         "text": h["text"], "text2": h["text2"], "hinted": h["hinted"]})
            save()
            print(f"  {it['id']:<16} {c:<3} {h['text']}" + ("   [hint used]" if h["hinted"] else
                                                          "   [hint REJECTED: lost the vehicle]" if h.get("hint_rejected") else ""))
    return rows


def report_a(rows, by_id):
    print("\n================ PART A: hint v2 on new Marathi sentences ================")
    lost = back = false_birds = worse = 0
    for r in rows:
        if r.get("tts_failed"):
            print(f"  TTS failed: {r['id']}"); continue
        it = by_id[r["id"]]
        is_birds = it["truth"]["instructions"][0][1] == "REPORT_BIRDS"
        o1, b1 = grade(it, r["first"], None if r["hinted"] else r["text2"], False)
        o2, b2 = grade(it, r["text"], r["text2"], r["hinted"])
        tag = ""
        if is_birds and not b1:
            lost += 1
            ok = r["hinted"] and b2 and o2 != "WRONG"
            back += ok
            tag = "BIRDS BACK" if ok else "birds lost" + (" (hint rejected)" if r["hint_rejected"] else "")
        if not is_birds and b2:
            false_birds += 1; tag = "!! FALSE BIRDS"
        if r["hinted"] and RANK[o2] < RANK[o1]:
            worse += 1; tag += " !! WORSE"
        if tag or o2 != "OK":
            print(f"  {r['id']:<16} {r['cond']:<3} {o1} -> {o2}  {tag}\n     listen 1 : {r['first']}"
                  + (f"\n     hint     : {r['hint_text']}" if r.get("hint_text") else ""))
    print(f"\nA: lost by listen 1 {lost} | back with v2 {back} | FALSE birds {false_birds} | worse {worse}")
    if lost < 3:
        print("A VERDICT: TOO FEW LOST (<3) to judge - HINT_MODE stays 'off'.")
    elif back * 3 >= lost and false_birds == 0 and worse == 0:
        print("A VERDICT: PASS - set HINT_MODE = 'v2' in sentinel_pipeline.py.")
    else:
        print("A VERDICT: FAIL - HINT_MODE stays 'off'.")


def part_g(files):
    print("\n================ PART G: Fix G with a silent second-listen callsign ================")
    rows = []
    for f in files:
        res = json.load(open(f, encoding="utf-8"))
        if res.get("testset") == "locked":
            raise SystemExit("Refusing: that is the LOCKED exam.")
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        its = {it["id"]: it for it in ts["items"]}
        rows += [(its[r["id"]], r, f"{res['testset']}:{r['id']}:{r['cond']}") for r in res["results"]
                 if r["id"] in its and r.get("heard2")]
    better, worse, new_wrong = [], [], []
    for it, r, tag in rows:
        sentinel_parse.FIXG_SILENT_CALLSIGN = False
        o1 = judge_full(it, r["heard"], r["heard2"], r.get("hinted", False))[0]
        sentinel_parse.FIXG_SILENT_CALLSIGN = True
        o2 = judge_full(it, r["heard"], r["heard2"], r.get("hinted", False))[0]
        sentinel_parse.FIXG_SILENT_CALLSIGN = False
        if RANK[o2] > RANK[o1]:
            better.append((tag, o1, o2, r["heard"], r["heard2"]))
        elif RANK[o2] < RANK[o1]:
            worse.append((tag, o1, o2, r["heard"], r["heard2"]))
            new_wrong += [tag] if o2 == "WRONG" else []
    for tag, o1, o2, h1, h2 in better + worse:
        print(f"  {'+' if RANK[o2] > RANK[o1] else '!!'} {tag:<26} {o1} -> {o2}\n      listen 1: {h1}\n      listen 2: {h2}")
    print(f"\nG: {len(rows)} transcripts with a second listen | better {len(better)} | worse {len(worse)} | new WRONG {len(new_wrong)}")
    ok = better and not worse and not new_wrong
    print("G VERDICT:", "PASS - set FIXG_SILENT_CALLSIGN = True in sentinel_parse.py." if ok else "FAIL - stays off.")


def main():
    files = sys.argv[1:]
    bad = [f for f in files if not os.path.isfile(f)]
    if not files or bad:
        raise SystemExit(f"Give the old result files (dev, dev2, step1). Not a file: {bad}  (nothing run, nothing paid)")
    todo = items()
    by_id = {it["id"]: it for it in todo}
    broken = [it["id"] for it in todo if grade(it, it["text"], None, False)[0] != "OK"]
    if broken:
        raise SystemExit(f"Scripted lines that do not score OK as perfect text (fix the script first): {broken}")
    part_g(files)
    print(f"\nPart A: {len(todo)} new lines x {len(CONDS)} noise levels: {len(todo)} TTS + about 90 STT, about Rs 6.")
    if input("Continue with Part A? [y/N] ").strip().lower() != "y":
        return
    os.makedirs("results", exist_ok=True)
    report_a(part_a(todo), by_id)
    print("\nPaste the whole output.")


if __name__ == "__main__":
    main()
