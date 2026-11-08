"""
Experiment A8 — hazard VOCABULARY hints for the vehicle channel.

The BIRDS_MR failure: "रनवे टू सेवन वर पक्षी आहेत" (birds on 27) heard as "पक्की आहे". It happened in
all 3 noisy Marathi clips, in BOTH listens (A7) - so a second listen cannot fix it. Prisma's keyterms
list biases it toward words we tell it to expect. Our list today has only English ATC words.

Is this the rejected idea from Day 3 (traffic list in keyterms)? No:
  - that hinted FLIGHT NUMBERS, which pushes Prisma toward the flight we expect -> hides a wrong one
  - this hints a fixed hazard VOCABULARY ("birds", "FOD") that is the same at every airport, every day.
    The worst it can do is make a "pakki" sound like "pakshi": a false bird report (checked, harmless),
    and we MEASURE that below.

Extra keyterms tested: पक्षी, पक्षी आहेत, birds, bird activity, FOD
RULE FIXED NOW (before seeing results). The hint goes live (vehicle channel only) only if ALL hold:
  1. the bird word comes back in at least 1/3 of the noisy bird clips where it was lost
  2. 0 FALSE bird reports on vehicle lines that did not mention birds
  3. no more vehicle lines get worse (vehicle, runway or request wrong / lost) than get better
No new TTS. Re-uses cached audio: every vehicle line in dev, dev2 and the scenarios.
Run:   python experiments/exp_a8.py results/dev_20261031_000600.json results/dev2_20261031_004232.json results/scenarios_20261103_032521.json
Cost:  one STT call per vehicle clip (~125)  ~ Rs 6
"""
import os
import sys
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [_REPO, os.path.join(_REPO, "experiments")]   # engine modules live at the repo root
os.chdir(_REPO)                                              # data paths (results/, testsets/, ...) are repo-relative
import json
import datetime

from gnani_client import stt
from sentinel_actions import analyse
from scoring import truth_of

HAZARD_TERMS = ["पक्षी", "पक्षी आहेत", "birds", "bird activity", "FOD"]


def jobs():
    out = []
    for f in sys.argv[1:]:
        res = json.load(open(f, encoding="utf-8"))
        if isinstance(res, list):                                     # scenarios file
            from scenarios import SCENARIOS
            for r in res:
                sc = SCENARIOS[r["scenario"]]
                for i, s in enumerate(r["steps"]):
                    if s["channel"] != "airside" or r["cond"] == "text":
                        continue
                    truth_a = analyse(s["said"], sc["airport"], sc["traffic"], "airside")
                    t = (truth_a["callsign"], [(x["runway"], x["action"]) for x in truth_a["instructions"]])
                    clean = f"audio_eval/scen/{r['scenario']}_{i}_{s['speaker']}.wav"
                    path = clean if r["cond"] == "clean" else clean.replace(".wav", f"_snr{r['cond']}.wav")
                    out.append((f"{r['scenario']}#{i}", r["cond"], sc["airport"], sc["traffic"], path, s["heard"], t))
            continue
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        items = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            it = items[r["id"]]
            if it["channel"] != "airside":
                continue
            t = (it["truth"]["callsign"], [tuple(x) for x in truth_of(it)[0]])
            clean = f"audio_eval/{ts['name']}/{r['id']}.wav"
            path = clean if r["cond"] == "clean" else clean.replace(".wav", f"_snr{r['cond'].replace('dB', '')}.wav")
            out.append((r["id"], r["cond"], it["airport"], it["traffic"], path, r["heard"], t))
    return out


def score(text, ap, traffic, truth):
    """How many of: vehicle, runway, request/report are right (0-3), and did it claim birds?"""
    a = analyse(text, ap, traffic, "airside")
    tcs, tins = truth
    got = {x["runway"]: x["action"] for x in a["instructions"] if x["valid"]}
    rw, act = tins[0]
    pts = (a["callsign"] == tcs) + (rw in got) + (got.get(rw) == act)
    birds = any(v == "REPORT_BIRDS" for v in got.values())
    return pts, birds


def main():
    todo = jobs()
    print(f"{len(todo)} vehicle clips\n")
    lost = back = false_birds = better = worse = 0
    rows = []
    for iid, cond, ap, traffic, path, heard, truth in todo:
        if not os.path.exists(path):
            print(f"  missing {path} - skipped"); continue
        t2 = stt(path, "airside", extra_keyterms=HAZARD_TERMS)
        p1, b1 = score(heard, ap, traffic, truth)
        p2, b2 = score(t2, ap, traffic, truth)
        is_birds = truth[1][0][1] == "REPORT_BIRDS"
        tag = ""
        if is_birds and not b1 and cond != "clean":
            lost += 1
            back += b2
            tag = "BIRDS BACK" if b2 else "birds still lost"
        if not is_birds and b2:
            false_birds += 1; tag = "!! FALSE BIRDS"
        better += p2 > p1
        worse += p2 < p1
        if tag or p2 != p1:
            print(f"  {iid:<14} {cond:5} {p1}/3 -> {p2}/3  {tag}\n     without hint: {heard}\n     with hint   : {t2}")
        rows.append({"id": iid, "cond": cond, "heard": heard, "heard_hint": t2, "score": [p1, p2], "birds": [b1, b2]})
    ok = lost and back * 3 >= lost and false_birds == 0 and worse <= better
    print(f"\nRESULT: lost bird words brought back {back}/{lost} | FALSE birds {false_birds} | lines better {better}, worse {worse}")
    print("RULE: >=1/3 back, 0 false birds, worse <= better ->", "PASS: add HAZARD_TERMS to the vehicle channel." if ok
          else "FAIL: no hint.")
    os.makedirs("results", exist_ok=True)
    out = f"results/exp_a8_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {out}. Paste the whole output.")


if __name__ == "__main__":
    main()
