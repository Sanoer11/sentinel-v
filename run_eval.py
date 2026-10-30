"""
Runs a test set and scores it honestly (problems #15, #17, #18, #19, #20).

  python run_eval.py testsets/dev.json --dry-run      # free: perfect transcripts, checks the pipeline
  python run_eval.py testsets/dev.json                # real: Timbre voices + radio noise + Prisma
  python run_eval.py testsets/locked_XXXX.json        # ONE-TIME exam on frozen code
  python run_eval.py testsets/human_XXXX.json --human # real people's recordings from my_voice/

Safety rules built in:
  - Locked sets refuse to run if code has uncommitted changes (git), and refuse to run twice.
  - Every result file records the git commit + parser fingerprint it was made with.
  - Locked runs print ONLY totals, never individual transcripts.
  - Human runs stop loudly if recordings are missing or misnamed.
"""
import os
import re
import sys
import json
import glob
import shutil
import hashlib
import argparse
import subprocess
import datetime
import numpy as np
import soundfile as sf

import sentinel_parse
from scoring import judge, summarize, fmt
from radio_sim import radio

NOISE = [None, 20, 10, 5, 0]          # None = clean (no radio)
COST_PER_CALL = 0.05                  # Rs, measured on the dashboard: 88 STT calls cost Rs 3.92


def git_state():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                        text=True).strip()
        return commit, bool(dirty)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, True


def parser_fingerprint():
    # ignore trailing blank lines/newline, which downloads sometimes strip
    text = open(sentinel_parse.__file__, encoding="utf-8").read().rstrip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def ledger(path="testsets/ledger.json"):
    return json.load(open(path)) if os.path.exists(path) else {}


def to_wav(src, dst):
    """Human recordings (.m4a) -> wav, needed to add radio noise on top. Uses ffmpeg if installed."""
    if src.endswith(".wav"):
        return src
    if not shutil.which("ffmpeg"):
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", dst], check=True)
    return dst


def human_files(items, folder):
    ids = {it["id"] for it in items}
    found, problems = [], []
    for f in sorted(glob.glob(os.path.join(folder, "*"))):
        m = re.match(r"([a-zA-Z]+)_([a-z]\d{3}[abv])\.(m4a|wav|mp3|aac|ogg)$", os.path.basename(f))
        if not m:
            problems.append(f"bad name (want name_id.m4a): {os.path.basename(f)}")
        elif m.group(2) not in ids:
            problems.append(f"id {m.group(2)} is not in this test set: {os.path.basename(f)}")
        else:
            found.append((f, m.group(1).lower(), m.group(2)))
    speakers = sorted({s for _, s, _ in found})
    for s in speakers:
        have = {i for _, sp, i in found if sp == s}
        missing = sorted(ids - have)
        if missing:
            problems.append(f"{s}: {len(missing)} lines not recorded: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
    return found, speakers, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testset")
    ap.add_argument("--dry-run", action="store_true", help="no API calls; perfect transcripts")
    ap.add_argument("--human", action="store_true", help="score recordings in my_voice/")
    ap.add_argument("--yes", action="store_true", help="skip the cost question")
    a = ap.parse_args()

    ts = json.load(open(a.testset, encoding="utf-8"))
    items = {it["id"]: it for it in ts["items"]}
    locked = ts["kind"] in ("locked", "human") and not a.dry_run
    commit, dirty = git_state()
    fp = parser_fingerprint()
    print(f"Test set {ts['name']} ({len(items)} lines) | git {commit} {'(UNCOMMITTED CHANGES)' if dirty else ''} | parser {fp}")

    if locked:
        if commit is None or dirty:
            raise SystemExit("STOP: locked/human sets need committed code. Run: git add -A && git commit -m 'freeze'")
        if ts["name"] in ledger():
            raise SystemExit(f"STOP: {ts['name']} was already used on {ledger()[ts['name']]['date']}. "
                             "Make a new one: python make_testset.py locked")

    # ---- build the job list: (item, condition, audio path or None) ----
    jobs = []
    if a.human:
        found, speakers, problems = human_files(ts["items"], "my_voice")
        for p in problems:
            print("  !", p)
        if not found:
            raise SystemExit("STOP: no usable recordings in my_voice/. See the recording sheet for names.")
        print(f"Found {len(found)} recordings from {len(speakers)} speaker(s): {', '.join(speakers)}")
        for f, spk, iid in found:
            jobs.append((items[iid], f"as recorded ({spk})", f))
            os.makedirs("audio_eval", exist_ok=True)
            try:
                w = to_wav(f, f"audio_eval/{spk}_{iid}.wav")
            except subprocess.CalledProcessError:
                print(f"  ! could not read {os.path.basename(f)} (damaged or empty file) - skipped")
                jobs.pop()
                continue
            if w:
                jobs.append((items[iid], f"radio 10dB ({spk})", ("radio", w, 10)))
        if not shutil.which("ffmpeg"):
            print("  (ffmpeg not installed: only 'as recorded' is tested. Install with: brew install ffmpeg)")
    else:
        for it in ts["items"]:
            for snr in NOISE:
                jobs.append((it, "clean" if snr is None else f"{snr}dB", None if snr is None else snr))

    calls = len(jobs)
    tts_calls = 0 if a.human else len(items)
    if not a.dry_run:
        print(f"This run makes {calls} STT + {tts_calls} TTS calls, about Rs {COST_PER_CALL * (calls + tts_calls):.0f}.")
        if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
            return

    from gnani_client import tts, stt
    results = []
    for it, cond, src in jobs:
        if a.dry_run:
            text = it["ideal"]
        else:
            if a.human:
                if isinstance(src, tuple):
                    _, w, snr = src
                    x, sr = sf.read(w)
                    path = w.replace(".wav", f"_snr{snr}.wav")
                    sf.write(path, radio(x, sr, snr, seed=int(hashlib.md5(path.encode()).hexdigest()[:8], 16)), 8000, subtype="PCM_16")
                else:
                    path = src
            else:
                clean = f"audio_eval/{ts['name']}/{it['id']}.wav"
                if not tts(it["text"], it["voice"], it["tts_model"], it["tts_lang"], clean):
                    continue
                if src is None:
                    path = clean
                else:
                    path = clean.replace(".wav", f"_snr{src}.wav")
                    if not os.path.exists(path):
                        x, sr = sf.read(clean)
                        seed = int(hashlib.md5(path.encode()).hexdigest()[:8], 16)
                        sf.write(path, radio(x, sr, src, seed=seed), 8000, subtype="PCM_16")
            text = stt(path, it["channel"])
        outcome, parsed = judge(text, it["airport"], it["traffic"],
                                it["truth"]["runway"], it["truth"]["callsign"])
        results.append({"id": it["id"], "cond": cond, "channel": it["channel"], "traps": it["traps"],
                        "said": it["text"], "heard": text, "outcome": outcome,
                        "parsed": [parsed["runway"], parsed["callsign"], parsed["problems"]]})
        if not locked:
            mark = {"OK": "  ", "AMBER": "a ", "FLAG": "~ ", "WRONG": "!!"}[outcome]
            print(f"{mark}{it['id']} {cond:<18} {outcome:<5} {text}")

    # ---- report ----
    print("\n================ RESULT ================")
    conds = []
    for r in results:
        if r["cond"] not in conds:
            conds.append(r["cond"])
    for c in conds:
        print(f"{c:<20} {fmt(summarize([r['outcome'] for r in results if r['cond'] == c]))}")
    print("\nBy kind of line (all conditions together):")
    for ch in ("tower", "pilot", "airside"):
        o = [r["outcome"] for r in results if r["channel"] == ch]
        if o:
            print(f"  {ch:<18} {fmt(summarize(o))}")
    print("\nTraps (how often a trap line ended WRONG):")
    for t in sorted({t for r in results for t in r["traps"]}):
        o = [r["outcome"] for r in results if t in r["traps"]]
        print(f"  {t:<26} WRONG {o.count('WRONG')}/{len(o)}")
    wrong = [r for r in results if r["outcome"] == "WRONG"]
    if wrong and not locked:
        print("\nEvery WRONG, so nothing is hidden:")
        for r in wrong:
            print(f"  {r['id']} {r['cond']}: said '{r['said']}'\n      heard '{r['heard']}' -> parsed {r['parsed'][:2]}")

    os.makedirs("results", exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/{ts['name']}_{'dry_' if a.dry_run else ''}{stamp}.json"
    json.dump({"testset": ts["name"], "git": commit, "dirty": dirty, "parser": fp,
               "dry_run": a.dry_run, "human": a.human, "results": results},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nSaved {out}  (git {commit}, parser {fp})")

    if locked:
        L = ledger()
        L[ts["name"]] = {"date": stamp, "git": commit, "parser": fp, "result_file": out}
        json.dump(L, open("testsets/ledger.json", "w"), indent=1)
        print(f"{ts['name']} is now USED. It can never be the exam again; make a new one for the next exam.")


if __name__ == "__main__":
    main()
