"""
Experiment A4 — two problems from dev + dev2 (600 clips), causes tested BEFORE any fix.

PART 1  Pilot readbacks lose the LAST digit ("Air India 836" for 8369): 19 of 192 noisy pilot
        clips, 0 of 48 clean. The callsign is the last word, and our radio adds a burst of
        squelch static right after it. Is the static the cause, or just noise?
        Test: the SAME clip, same noise, with the squelch tail removed.
        RULE (fixed now): building a squelch-tail trimmer is worth it only if removing the tail
        brings back the full callsign in 10+ of these clips. Otherwise the cause is noise, and the
        answer stays "callsign incomplete - say again".

PART 2  Vehicles have no look-alike protection. dev2 e000v (10 dB): Prisma heard "Bird Chaser 2"
        for Bird Chaser 4 while Bird Chaser 2 was active. Only a broken runway stopped it being a
        silent WRONG. Vehicle numbers are one digit, so any slip lands on another active vehicle.
        Test: ask every vehicle call again in verbatim. Do the two listens agree?
        RULE (fixed now): a "both listens must agree on the vehicle number" check goes live only if
        it catches every wrong vehicle seen AND flags no more than 10% of vehicle calls that were right.

No new TTS. Re-uses the cached dev / dev2 audio.
Run:   python exp_a4.py results/dev_20261031_000600.json results/dev2_20261031_004232.json
Cost:  ~19 (part 1) + ~110 (part 2) STT calls  ~ Rs 7
"""
import os
import re
import sys
import json
import hashlib
import datetime
import soundfile as sf

from gnani_client import stt
from radio_sim import radio
from sentinel_parse import extract
from scoring import judge


def paths(ts_name, iid, cond):
    clean = f"audio_eval/{ts_name}/{iid}.wav"
    return clean, (clean if cond == "clean" else clean.replace(".wav", f"_snr{cond.replace('dB', '')}.wav"))


def last_digit_lost(heard, cs):
    num = cs[3:]
    return re.search(r"\b" + num[:-1] + r"\b", heard) is not None and num not in heard


def main():
    os.makedirs("audio_eval/exp_a4", exist_ok=True)
    log = {"part1": [], "part2": []}
    p1, p2 = [], []
    for f in sys.argv[1:]:
        res = json.load(open(f, encoding="utf-8"))
        ts = json.load(open(f"testsets/{res['testset']}.json", encoding="utf-8"))
        items = {it["id"]: it for it in ts["items"]}
        for r in res["results"]:
            it = items[r["id"]]
            if r["id"].endswith("b") and r["cond"] != "clean" and last_digit_lost(r["heard"], it["truth"]["callsign"]):
                p1.append((ts["name"], r, it))
            if it["channel"] == "airside":
                first = extract(r["heard"], it["airport"], set(it["traffic"]))
                if first["callsign"]:
                    p2.append((ts["name"], r, it, first))

    print(f"PART 1: {len(p1)} pilot clips that lost the last digit\n")
    back = 0
    for name, r, it in p1:
        clean, noisy = paths(name, r["id"], r["cond"])
        if not os.path.exists(clean):
            print(f"  missing {clean} - skipped"); continue
        x, sr = sf.read(clean)
        snr = int(r["cond"].replace("dB", ""))
        seed = int(hashlib.md5(noisy.encode()).hexdigest()[:8], 16)      # identical noise to the original run
        p = f"audio_eval/exp_a4/{name}_{r['id']}_snr{snr}_notail.wav"
        sf.write(p, radio(x, sr, snr, seed=seed, squelch_tail=False), 8000, subtype="PCM_16")
        t = stt(p, it["channel"])
        full = it["truth"]["callsign"][3:] in t
        back += full
        print(f"  {r['id']} {r['cond']:5} truth {it['truth']['callsign']:<8} {'BACK' if full else 'still lost'}")
        print(f"     with tail: {r['heard']}\n     no tail  : {t}")
        log["part1"].append({"id": r["id"], "cond": r["cond"], "with_tail": r["heard"], "no_tail": t, "full": full})
    print(f"\nPART 1 RESULT: full callsign back in {back} of {len(p1)}.  RULE 10+ ->",
          "PASS: build a squelch-tail trimmer." if back >= 10 else "FAIL: cause is noise, keep 'say again'.")

    print(f"\nPART 2: {len(p2)} vehicle calls where the first listen named a vehicle\n")
    right_agree = right_disagree = wrong_caught = wrong_missed = 0
    for name, r, it, first in p2:
        _, p = paths(name, r["id"], r["cond"])
        if not os.path.exists(p):
            print(f"  missing {p} - skipped"); continue
        t2 = stt(p, it["channel"], fmt="verbatim")
        second = extract(t2, it["airport"], set(it["traffic"]))
        agree = second["callsign"] == first["callsign"]
        right = first["callsign"] == it["truth"]["callsign"]
        if right and agree: right_agree += 1
        elif right: right_disagree += 1
        elif not agree: wrong_caught += 1
        else: wrong_missed += 1
        mark = "" if right and agree else ("  <-- disagree (extra flag)" if right else ("  <-- WRONG VEHICLE CAUGHT" if not agree else "  <-- WRONG VEHICLE MISSED"))
        print(f"  {r['id']} {r['cond']:5} truth {it['truth']['callsign']:<12} first {first['callsign']:<12} second {second['callsign']}{mark}")
        if mark:
            print(f"     first : {r['heard']}\n     second: {t2}")
        log["part2"].append({"id": r["id"], "cond": r["cond"], "heard": r["heard"], "heard2": t2,
                             "first": first["callsign"], "second": second["callsign"], "truth": it["truth"]["callsign"]})
    n_right = right_agree + right_disagree
    rate = right_disagree / n_right if n_right else 0
    ok = wrong_missed == 0 and rate <= 0.10
    print(f"\nPART 2 RESULT: right & agree {right_agree} | right but disagree {right_disagree} ({100*rate:.0f}%) "
          f"| wrong caught {wrong_caught} | wrong MISSED {wrong_missed}")
    print("RULE: no wrong missed AND extra flags <= 10% ->", "PASS: vehicle check goes live." if ok else "FAIL: check stays off.")
    os.makedirs("results", exist_ok=True)
    out = f"results/exp_a4_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(log, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Saved {out}. Paste the whole output.")


if __name__ == "__main__":
    main()
