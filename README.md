# Sentinel-V

**Hears the tower. Watches the runway. Speaks before two clearances collide.**

[![CI](https://github.com/Sanoer11/sentinel-v/actions/workflows/ci.yml/badge.svg)](https://github.com/Sanoer11/sentinel-v/actions/workflows/ci.yml)
**Live:** https://sentinel-v-one.vercel.app - replay every measured run in a browser, nothing to install.

Sentinel-V listens to Indian ATC and airside radio - English tower and pilot calls, Hindi, Hinglish and Marathi vehicle
calls - at Delhi (VIDP), Mumbai (VABB) and Pune (VAPO). It keeps track of who holds each runway, checks every
readback against the clearance, and **says the alert out loud** when two clearances collide or a readback is wrong.

Built for Gnani AI's Great Indian AI Internship Challenge. Research prototype on synthetic voices - **not for
operational use**.

## Why
On 23 Aug 2023 at Delhi, Vistara VTI725 was cleared for take-off on runway 29R while Vistara VTI926, just landed on 29L,
was told to cross 29R ([ASN](https://cdn.aviation-safety.net/wikibase/344824),
[Business Standard](https://business-standard.com/amp/india-news/dgca-to-probe-runway-incursion-involving-vistara-plane-at-delhi-airport-123082300384_1.html)).
Both clearances went out by voice. Sentinel-V is a second pair of ears on that frequency.

## Gnani models used
| Model | What it does here |
|---|---|
| **Gnani Prisma v3.0** (speech-to-text) | Every radio call. `transcribe` first; a `verbatim` second listen only when a runway or flight number comes out glued ("290" for "two niner"); a hazard-word hint for vehicle calls when the first listen is unclear. |
| **Gnani Timbre v3.0** (text-to-speech) | The spoken alerts (voice Devansh, phrase clips recorded ahead, joined in ~3 ms), the practice-set voices, and the film's narration (voice Shubham). |
| **Gnani Timbre v2.5** | Voices kept unseen for the one-time locked exam (Pranav, Kaveri, Shlok, Devika, Ishaan). |

No other speech or language model is used. The runway engine is rule-based Python (standard library only): no
generative model makes a decision, and the same words always give the same verdict.

## How it works
1. **Hear** - radio audio -> Prisma -> text (median 0.49 s per call).
2. **Read** - parse callsign, runway, instruction (cross / hold short / line up / take-off / land / go around / stop /
   conditional "behind"), in English, Hindi, Hinglish and Marathi; ICAO digits ("niner", "tree", "fife").
3. **Track** - a runway state machine: who holds which runway, including crossing runways (Mumbai 09/27 x 14/32).
4. **Check** - every readback against its clearance: wrong runway, wrong instruction, wrong or look-alike callsign
   (IFLY 5134 vs 5124), missing STOP / hold-short confirmation.
5. **Speak** - RED alerts as a short phrase in a fixed voice ("Runway conflict, two niner right, Vistara niner two six").
   When something was not heard clearly, it says so (AMBER "confirm") instead of guessing.

## Results - all measured, nothing estimated
Scenarios = whole radio sequences (8: Delhi 2023, Mumbai 2024, hold-short read back as crossing, twin callsigns,
STOP, Marathi bird chaser, Hinglish Follow Me, normal Delhi traffic), spoken by Timbre, passed through a simulated VHF
radio, heard by Prisma, judged by the engine. A run is "on time" only if every expected alert comes at the call it
belongs to.

| | Practice set (tuned on, current engine) | **Locked exam** (run once, `freeze-v3`, unseen voices + noise) |
|---|---|---|
| Scenarios, clean audio | 8 / 8 on time | **7 / 8** |
| Scenarios, 10 dB radio noise | 147 / 160 on time (20 noise recordings) | **27 / 40** (5 new noise recordings) |
| False RED in normal traffic, 10 dB | 2 / 20 | **1 / 5** |
| Deliberately wrong readbacks missed | **0 / 75** | **0 / 90** |
| Correct readbacks shown RED | 15 / 285 | 13 / 300 |
| Single lines shown as fine or probable but not what was said | - | **3 / 930** (all at 5 or 0 dB; 0 at clean, 20 and 10 dB) |
| Prisma time per call (median) | 0.49 s | 0.46 s |
| Spoken alert ready after the call ends (median) | - | 0.48 s (engine 0.1 ms + voice join ~3 ms) |

**What the locked exam showed.** With an unseen tower voice, Prisma often turned "two niner right" into "29, arrived"
or "290", and the airline word into digits ("35134" for "IFLY 5134"). The engine then says "confirm" (AMBER) instead
of RED - so Delhi 2023 and hold-short-as-crossing were caught on time in 0 of 5 noisy runs each, although wrong
readbacks were still never passed as correct (0 / 90). The engine was partly tuned to the practice voices; this is the
honest number: the locked figures are for `freeze-v3` and stay as they are.

**After the exam** (not in the locked numbers; judged only on practice data, never on the exam's transcripts).
The exam's voices are used up, so they were used for one more practice run (10 dB, new noise recordings 200-209).
Every remaining miss was traced to one exact cause and counted on all saved transcripts before any code (A17):

| Cause (evidence) | Fix | Result |
|---|---|---|
| "two niner right" heard as "runway 290, right" (first two digits right 61/61, side right 48/48) | read as 29R, AMBER; steps back if the second listen disagrees | 13 runs better |
| "Vistara niner two six" heard as "Tara 9026" (10/10) | undo the "niner" 0 if exactly one flight fits, AMBER | 1 better |
| crossing call with the callsign lost was AMBER "maybe the same aircraft" | an aircraft cannot cross the runway it is taking off from: RED | 2 better |
| "clear for takeoff" / "cleared to take off" not read as a take-off | both read as TAKEOFF | 1 better |
| tower callsign lost: trust the instruction anyway (Fix X) | - | **failed** (2 correct readbacks turned RED), off |

| Practice data (designed on it, so not a held-out score) | before A17 | after A17 |
|---|---|---|
| Exam voices, new noise: scenarios on time | 62 / 80 | **70 / 80** |
| Delhi 2023 with those voices | 4 / 10 | **9 / 10** |
| Earlier practice, 10 dB | 137 / 160 | **147 / 160** |
| Wrong readbacks missed | 0 | 0 |
| False RED in normal traffic | 2 / 10 and 2 / 20 | unchanged |
| Single lines shown fine but wrong (864 saved lines) | 0 | 0 |

Kept on purpose: a pilot callsign with a misheard digit that is on no flight ("Akasa Air 113") stays RED. A real
stranger taking a clearance looks exactly the same, so turning it AMBER would hide real errors.
A16 ("29, arrived" = 29R) failed its rule: only 3 calls, one voice. Off.
The held-out check for these fixes is new human audio: `python run_scenarios.py --human` (own-voice recordings,
run once on committed code, new noise 300-304).

## Limits
- Radio only: no radar or surveillance, so an aircraft that moves without a radio call is invisible.
- Synthetic voices (Gnani Timbre) through a simulated radio; not yet tested on live ATC audio.
- Hold times are assumptions; "runway vacated" can be misheard, which keeps a runway busy (one of the 2 practice false REDs).
- A misheard callsign digit cannot be told apart from a real pilot error, so it comes out RED "confirm callsign" (the 2 practice false REDs at 10 dB with the exam voices).
- Every miss is listed with its reason on the site (Results and Limits).

## How it was built: experiments with rules written first
Each fix (A1-A17) had its pass/fail rule written in its `exp_a*.py` file **before** the result, was judged on saved
transcripts and fresh noise, and stayed off if it failed. Examples: A15 (above); A14 kept a runway heard glued ("290, right") as a
*maybe* 29R and turned 4 of 6 silent Delhi misses into AMBER "possible runway conflict" (pass); reading "Tara" as
"Vistara" removed 17 flags but caused 2 false REDs (fail, kept off). All of them are on the site under Experiments.

## Run it
```
pip install -r requirements-ci.txt
python -m pytest -q test_state.py test_actions.py test_scoring.py test_client.py test_pipeline.py test_voice.py
```
The tests need no API key (they use a fake Prisma/Timbre). For live runs put `GNANI_API_KEY=...` in `.env` (never
committed), then `python run_scenarios.py --cond clean` or `python run_eval.py testsets/dev.json`.
The site: `cd web && npm ci && npm run dev` (data is exported by `python export_web.py`).

| Path | What |
|---|---|
| `sentinel_parse.py`, `sentinel_actions.py`, `sentinel_state.py` | the engine: parsing, instructions, runway state + readback check |
| `sentinel_pipeline.py`, `gnani_client.py` | Prisma listens, Timbre, retries |
| `sentinel_voice.py` | spoken alerts |
| `scenarios.py`, `run_scenarios.py`, `make_testset.py`, `run_eval.py` | scenarios, test sets, the locked exam |
| `exp_a*.py` | every experiment, with its rule |
| `web/` | the public site (Next.js), deployed on Vercel |

## Data and safety
All audio is synthetic (Gnani Timbre) or synthetic noise; no real ATC recordings are used or published. The real
incidents are re-voiced from public reports. API keys live only in `.env`; a pre-commit hook blocks keys and audio.

## Team
**Sanoer Soni** (B.Tech ECE, AI/ML, MIT-WPU Pune) - everything: speech pipeline, runway engine, readback check,
experiments, alert voice, site and film.
