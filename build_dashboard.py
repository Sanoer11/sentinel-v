"""
Demo dashboard for the screen video and the posts: replays saved scenario runs through the FROZEN engine and
writes one self-contained page, dashboard/index.html, plus its audio in dashboard/audio/ (never committed: *.wav).

  python build_dashboard.py results/scenarios_A.json results/scenarios_B.json ...
  open dashboard/index.html

What it shows, per scenario and per run (clean / 10 dB noise recording n):
  - the airport's runways, lit up with who holds each one after every call (the engine's runway picture)
  - each radio call: what was SAID (the script) next to what Prisma HEARD, the engine's verdict, its alerts
  - the radio audio of each call and the spoken RED alert, played in order (Play / Step)
  - honest numbers over every run given: on time / late / missed, false RED in normal traffic, alert delay
Nothing here is re-heard: the transcripts are the saved ones, so the page shows exactly what the runs measured.
Alert voices are joined from the cached phrase clips (sentinel_voice.prepare records any missing ones: a few TTS).
"""
import os
import sys
import json
import shutil
import statistics
from collections import Counter, defaultdict

import sentinel_state
from scenarios import SCENARIOS
from sentinel_state import RunwayEngine, STRIPS, INTERSECTING
from sentinel_parse import AIRPORTS

OUT = "dashboard"
DESC = {
    "DEL_2023": ("Delhi, 23 Aug 2023 (real event)", "VTI926 told to cross 29R while VTI725 was cleared for take-off on 29R."),
    "BOM_2024": ("Mumbai, 8 Jun 2024 (real event)", "IFLY 6053 cleared to land on 27 while Air India 657 was taking off on 27."),
    "HOLD_AS_CROSS": ("Delhi, constructed", "A 'hold short' read back as 'crossing' while 29R is in use."),
    "TWIN_CALLSIGN": ("Delhi, constructed", "IFLY 5124 reads back the landing clearance meant for IFLY 5134."),
    "STOP": ("Pune, constructed", "'Stop immediately' during a take-off - and the pilot's confirmation."),
    "BIRDS_MR": ("Mumbai, constructed - Marathi", "A Bird Chaser reports birds on 27 while a departure is cleared on it."),
    "VEHICLE_HI": ("Delhi, constructed - Hinglish", "A Follow Me asks to cross 28 while an aircraft is cleared to land on it."),
    "NORMAL_DEL": ("Delhi, normal traffic", "Five clean clearances. Any RED here is a false alarm."),
}


def radio_path(name, i, spk, cond, seed, folder="scen"):
    clean = f"audio_eval/{folder}/{name}_{i}_{spk}.wav"
    if cond == "clean":
        return clean
    return clean.replace(".wav", f"_snr{cond}.wav" if seed == 0 else f"_snr{cond}_n{seed}.wav")


def snapshot(eng, t):
    return [{"strip": s, "cs": o["cs"], "action": o["action"], "rw": o["rw"], **({"maybe": o["maybe"]} if o.get("maybe") else {})}
            for s, occ in eng.occ.items() for o in occ if o.get("until", 1e9) > t]


def _copy_wav(src, rel_base, out):
    rel = f"{rel_base}.wav"
    shutil.copyfile(src, f"{out}/{rel}")
    return rel


def replay(run, voice_ok, tts, out=OUT, media=None):
    """The saved transcripts through the frozen engine, keeping the runway picture after every call.
    media(src_wav, rel_base, out) -> published relative path (default: copy the wav); export_web.py passes an mp3 encoder."""
    media = media or _copy_wav
    sc = SCENARIOS[run["scenario"]]
    eng = RunwayEngine(sc["airport"], sc["traffic"], sc["phases"])
    seed = run.get("seed", 0)
    tag = f"{run['scenario']}_{run['cond']}_n{seed}"
    steps = []
    for i, (s, (t, ch, spk, said)) in enumerate(zip(run["steps"], sc["steps"])):
        rec = eng.call(s["t"], s["channel"], s["heard"], s["heard2"], hinted=s.get("hinted", False))
        audio = None
        src = radio_path(run["scenario"], i, spk, run["cond"], seed)
        if os.path.exists(src):
            audio = media(src, f"audio/{tag}_{i}", out)
        spoken = None
        if voice_ok:
            import sentinel_voice
            al = sentinel_voice.pick(rec["alerts"])
            if al:
                phr = sentinel_voice.phrases(al)
                try:
                    tmp = f"{out}/audio/_alert_tmp.wav"
                    sentinel_voice.assemble(phr, tmp)
                    path = media(tmp, f"audio/{tag}_{i}_alert", out)     # always a different file than tmp
                    os.remove(tmp)
                    spoken = {"file": path, "says": sentinel_voice.sentence(phr)}
                except Exception as e:                       # a missing clip must not break the page
                    spoken = {"file": None, "says": sentinel_voice.sentence(phr), "error": str(e)[:80]}
        steps.append({"t": s["t"], "channel": s["channel"], "speaker": spk, "said": said, "heard": s["heard"],
                      "heard2": s["heard2"], "hinted": s.get("hinted", False), "status": rec["analysis"]["status"],
                      "latency": s.get("latency_s"), "audio": audio, "spoken": spoken,
                      # what the engine made of the words: the callsign it settled on, and its own notes
                      # ("Tara, 926" -> VTI926: airline word not heard, matched by the flight number)
                      "read": rec["analysis"].get("callsign"), "notes": list(rec["analysis"].get("amber", [])),
                      "alerts": [{"level": a["level"], "kind": a["kind"], "text": a["text"]} for a in rec["alerts"]],
                      "picture": snapshot(eng, s["t"])})
    tail = eng.tick(run["steps"][-1]["t"] + 15)
    # verdict, the same rules as run_scenarios.py
    misses = late = 0
    for i, kind, lvl in sc.get("expect", []):
        hit = [j for j in range(i, len(steps)) if any(a["kind"] == kind and a["level"] == lvl for a in steps[j]["alerts"])]
        misses += not hit
        late += bool(hit) and hit[0] != i
    reds = sum(a["level"] == "RED" for st in steps for a in st["alerts"]) + sum(a["level"] == "RED" for a in tail)
    false_red = bool(sc.get("no_red") and reds)
    other = any(a["level"] == "RED" for st in steps for a in st["alerts"])
    verdict = ("FALSE RED" if false_red else "OTHER-RED" if misses and other else "MISSED" if misses
               else "LATE" if late else "ON TIME")
    return {"scenario": run["scenario"], "cond": run["cond"], "seed": seed, "verdict": verdict,
            "false_red": false_red, "steps": steps}


def main():
    files = [f for f in sys.argv[1:] if f.endswith(".json")]
    if not files:
        raise SystemExit("use: python build_dashboard.py results/scenarios_<A>.json [more files]")
    runs = [r for f in files for r in json.load(open(f, encoding="utf-8")) if r["cond"] != "text"]
    seen, uniq = set(), []
    for r in runs:                                   # one copy of each (scenario, cond, seed): the latest file wins
        k = (r["scenario"], r["cond"], r.get("seed", 0))
        if k in seen:
            uniq = [u for u in uniq if (u["scenario"], u["cond"], u.get("seed", 0)) != k]
        seen.add(k)
        uniq.append(r)
    os.makedirs(f"{OUT}/audio", exist_ok=True)
    voice_ok, tts = False, None
    try:
        import soundfile  # noqa: F401
        import sentinel_voice
        from gnani_client import tts
        for name in {r["scenario"] for r in uniq}:   # records only the phrase clips that are missing (cached)
            sc = SCENARIOS[name]
            sentinel_voice.prepare(tts, sc["airport"], sc["traffic"])
        voice_ok = True
    except (Exception, SystemExit) as e:             # no key / no soundfile: the page still builds, without alert audio
        print(f"  (alert voices skipped: {str(e)[:100]})")
    data = [replay(r, voice_ok, tts) for r in sorted(uniq, key=lambda r: (r["scenario"], r["cond"] != "clean", r.get("seed", 0)))]

    # honest numbers over every run on the page
    by = defaultdict(Counter)
    for d in data:
        by[(d["scenario"], "clean" if d["cond"] == "clean" else f"{d['cond']} dB")][d["verdict"]] += 1
    lat = [s["latency"] for d in data for s in d["steps"] if s["latency"]]
    normal = [d for d in data if SCENARIOS[d["scenario"]].get("no_red")]
    stats = {
        "runs": len(data),
        "on_time": sum(d["verdict"] == "ON TIME" for d in data),
        "late": sum(d["verdict"] == "LATE" for d in data),
        "noisy": sum(d["cond"] != "clean" for d in data),
        "normal_runs": len(normal), "false_red": sum(d["false_red"] for d in normal),
        "prisma_median": round(statistics.median(lat), 2) if lat else None,
        "table": {f"{k[0]}|{k[1]}": dict(v) for k, v in sorted(by.items())},
    }
    geo = {ap: {"strips": [f"{a}/{b}" for a, b in STRIPS[ap]], "cross": [list(x) for x in INTERSECTING.get(ap, [])],
                "name": AIRPORTS[ap]["name"]} for ap in STRIPS}
    meta = {k: {"where": v[0], "what": v[1], "airport": SCENARIOS[k]["airport"],
                "no_red": bool(SCENARIOS[k].get("no_red"))} for k, v in DESC.items()}
    page = open("dashboard_template.html", encoding="utf-8").read()
    blob = json.dumps({"runs": data, "stats": stats, "geo": geo, "meta": meta}, ensure_ascii=False)
    page = page.replace("/*__DATA__*/null", blob.replace("</", "<\\/"))
    open(f"{OUT}/index.html", "w", encoding="utf-8").write(page)
    print(f"Wrote {OUT}/index.html: {len(data)} runs ({stats['on_time']} on time, {stats['late']} late), "
          f"audio in {OUT}/audio/  ->  open {OUT}/index.html")


if __name__ == "__main__":
    main()
