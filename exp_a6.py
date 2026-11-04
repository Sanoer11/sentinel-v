"""
Experiment A6 — fix the false RED "WRONG CALLSIGN" alarms without weakening real catches.

15 correct readbacks got a RED "WRONG CALLSIGN" because Prisma slipped a digit in noise
(8496 heard as 8498, 5770 as 5772). The text looks exactly like a real pilot error.
Idea: hear the SAME readback audio again in verbatim, with NO tower context (not circular).
  - a digit slip by Prisma is random noise -> the second listen often hears another number
  - a pilot's real wrong number is in the audio -> both listens hear it
Rule in the engine: listen 2 hears the CLEARED number      -> AMBER "callsign unclear: listen 1 8498, listen 2 8496 - confirm"
                    listen 2 hears the same wrong number    -> RED stays ("heard the same in both listens")
                    listen 2 hears nothing / a third number -> RED stays (not evidence of a slip)
                    (never green: a disagreement is never shown as a match)

RULES FIXED NOW (before seeing results). Goes live only if ALL hold:
  1. at least 1/3 of the false REDs become AMBER
  2. at most 10% of the real wrong-callsign catches drop from RED to AMBER
  3. no wrong readback ends as MATCH
No new TTS: re-uses cached audio.
Run:   python exp_a6.py results/dev_20261031_000600.json results/dev2_20261031_004232.json results/step1_20261031_013014.json
Cost:  one STT call per RED callsign mismatch (~60)  ~ Rs 3
"""
import os
import sys
import json
import datetime

from gnani_client import stt
from sentinel_state import RunwayEngine
from scoring import phases_of


def audio_path(ts_name, iid, cond):
    clean = f"audio_eval/{ts_name}/{iid}.wav"
    return clean if cond == "clean" else clean.replace(".wav", f"_snr{cond.replace('dB', '')}.wav")


def main():
    rows = []
    fr = fr_fixed = tc = tc_lost = became_match = 0
    for f in sys.argv[1:]:
        res = json.load(open(f, encoding="utf-8"))
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        items = {it["id"]: it for it in ts["items"]}
        got = {(r["id"], r["cond"]): r for r in res["results"]}
        print(f"\n===== {ts['name']} =====")
        for (iid, cond), rb in got.items():
            it = items[iid]
            if it["channel"] != "pilot" or (iid[:-1] + "a", cond) not in got:
                continue
            tw = got[(iid[:-1] + "a", cond)]
            ph = {**(phases_of(items[iid[:-1] + "a"]) or {}), **(phases_of(it) or {})}
            e = RunwayEngine(it["airport"], it["traffic"], ph)
            e.call(0, "tower", tw["heard"], tw.get("heard2"))
            rec = e.call(4, "pilot", rb["heard"])
            p = rec.get("pending")
            if not p or p.get("verdict") != "MISMATCH" or p.get("why_kind") != "callsign":
                continue
            path = audio_path(ts["name"], iid, cond)
            if not os.path.exists(path):
                print(f"  missing {path} - skipped"); continue
            t2 = stt(path, "pilot", fmt="verbatim")
            rec = e.recheck_readback(rec, t2)
            still_red = any(a["level"] == "RED" for a in rec["alerts"])
            wrong_rb = it["truth"]["callsign"] not in it["traffic"] or any(t.startswith("wrong_readback") for t in it["traps"])
            if wrong_rb:
                tc += 1; tc_lost += not still_red; became_match += p.get("verdict") == "MATCH"
            else:
                fr += 1; fr_fixed += not still_red
            tag = ("REAL wrong readback " + ("still RED" if still_red else "<-- dropped to AMBER")) if wrong_rb \
                else ("false RED " + ("<-- FIXED, now AMBER" if not still_red else "still RED"))
            print(f"  {iid} {cond:5} {tag}\n     pilot   : {rb['heard']}\n     listen 2: {t2}\n     shown   : {rec['alerts'][0]['text'] if rec['alerts'] else '-'}")
            rows.append({"set": ts["name"], "id": iid, "cond": cond, "heard": rb["heard"], "heard_verbatim": t2,
                         "real_wrong": wrong_rb, "still_red": still_red})
    ok = fr and fr_fixed * 3 >= fr and tc_lost <= 0.10 * tc and became_match == 0
    print(f"\nRESULT: false REDs fixed {fr_fixed}/{fr} | real catches dropped to amber {tc_lost}/{tc} | wrong readbacks shown as MATCH {became_match}")
    print("RULE: >=1/3 fixed, <=10% dropped, 0 MATCH ->", "PASS: second listen goes live." if ok else "FAIL: stays off.")
    os.makedirs("results", exist_ok=True)
    out = f"results/exp_a6_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {out}. Paste the whole output.")


if __name__ == "__main__":
    main()
