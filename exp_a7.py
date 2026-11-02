"""
Experiment A7 — can a second, verbatim listen of the SAME audio recover an instruction word that
push-to-talk or noise removed, when the runway itself was heard?

Why: the two 10 dB scenario FAILs lost exactly one word each:
  HOLD_AS_CROSS  "Crossing runway 29 right"  -> "Asking runway 29 right"
  BIRDS_MR       "रनवे टू सेवन वर पक्षी आहेत" -> "runway 27 वर पक्की आहे"
and the same pattern sits in ~100 dev/dev2/step1 readbacks ("Taxiway runway 09", "Taking short ...").
A1 showed transcribe and verbatim CAN disagree on words ("29 left" vs "two nine eleven"), but A6 showed
they agree on noisy digits. So this has to be measured, not assumed.
It is not circular: no tower words are given to Prisma.

RULE FIXED NOW (before seeing results). INSTRUCTION_SECOND_LISTEN goes live only if BOTH:
  1. the second listen gives the RIGHT instruction in at least 20% of these clips
  2. it gives a DIFFERENT (wrong) instruction in 0 clips
     (one wrong fill = it can invent a "crossing" or a "hold short": that is never acceptable)
No new TTS. Re-uses cached audio.
Run:   python exp_a7.py results/dev_20261031_000600.json results/dev2_20261031_004232.json \
                        results/step1_20261031_013014.json results/scenarios_20261103_025027.json
Cost:  one STT call per clip that qualifies (~110)  ~ Rs 6
"""
import os
import sys
import json
import datetime

from gnani_client import stt
from sentinel_parse import normalize
from sentinel_actions import instructions
from scoring import truth_of


def empty_runways(text, airport, channel):
    return [x["runway"] for x in instructions(normalize(text), airport, channel)
            if x["valid"] and x["action"] is None and not x["conflict"]]


def jobs():
    out = []
    for f in sys.argv[1:]:
        res = json.load(open(f, encoding="utf-8"))
        if isinstance(res, list):                          # scenarios file
            from scenarios import SCENARIOS
            for r in res:
                if r["cond"] == "text":
                    continue
                sc = SCENARIOS[r["scenario"]]
                for i, s in enumerate(r["steps"]):
                    ap, ch = sc["airport"], s["channel"]
                    truth = {x["runway"]: x["action"] for x in instructions(normalize(s["said"]), ap, ch)}
                    clean = f"audio_eval/scen/{r['scenario']}_{i}_{s['speaker']}.wav"
                    path = clean if r["cond"] == "clean" else clean.replace(".wav", f"_snr{r['cond']}.wav")
                    for rw in empty_runways(s["heard"], ap, ch):
                        out.append((f"{r['scenario']}#{i}", r["cond"], ap, ch, path, s["heard"], rw, truth.get(rw)))
            continue
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        items = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            it = items[r["id"]]
            truth = {rw: act for rw, act in truth_of(it)[0]}
            clean = f"audio_eval/{ts['name']}/{r['id']}.wav"
            path = clean if r["cond"] == "clean" else clean.replace(".wav", f"_snr{r['cond'].replace('dB', '')}.wav")
            for rw in empty_runways(r["heard"], it["airport"], it["channel"]):
                out.append((r["id"], r["cond"], it["airport"], it["channel"], path, r["heard"], rw, truth.get(rw)))
    return out


def main():
    todo = jobs()
    print(f"{len(todo)} clips: a real runway was heard but no instruction for it\n")
    right = wrong = none = 0
    rows = []
    for iid, cond, ap, ch, path, heard, rw, truth in todo:
        if not os.path.exists(path):
            print(f"  missing {path} - skipped"); continue
        t2 = stt(path, ch, fmt="verbatim")
        got = {x["runway"]: x for x in instructions(normalize(t2), ap, ch)}.get(rw)
        act = got["action"] if got and not got["conflict"] else None
        if act is None:
            none += 1; tag = "still none"
        elif act == truth:
            right += 1; tag = "RIGHT"
        else:
            wrong += 1; tag = f"!! WRONG ({act}, truth {truth})"
        print(f"  {iid:<16} {cond:5} rw {rw:<4} truth {str(truth):<12} -> {tag}\n     listen 1: {heard}\n     listen 2: {t2}")
        rows.append({"id": iid, "cond": cond, "runway": rw, "truth": truth, "heard": heard, "heard_verbatim": t2, "got": act})
    n = right + wrong + none
    ok = n and right / n >= 0.20 and wrong == 0
    print(f"\nRESULT: {n} clips | right {right} ({100 * right / max(n, 1):.0f}%) | WRONG {wrong} | still none {none}")
    print("RULE: >= 20% right and 0 wrong ->", "PASS: set INSTRUCTION_SECOND_LISTEN = True" if ok else "FAIL: stays off.")
    os.makedirs("results", exist_ok=True)
    out = f"results/exp_a7_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {out}. Paste the whole output.")


if __name__ == "__main__":
    main()
