# Sentinel-V — one-page pitch

**A second pair of ears for the control tower.** For tower controllers: it warns, the controller decides.
Built on Gnani Prisma and Gnani Timbre.

**Live:** https://sentinel-v-one.vercel.app · **Demo video (3 min):** https://drive.google.com/file/d/1cs33RWkTip79Yo0wmzfe7f04-aPNpzzo/view · **Short film:** https://lnkd.in/p/ddndXZeH · **Code:** https://github.com/Sanoer11/sentinel-v

## The problem
Runway safety in India still runs on voice. On 23 August 2023 at Delhi, one Vistara aircraft was cleared to cross
runway 29R and another was cleared to take off from the same runway. A pilot noticed and the take-off was stopped.
Both clearances were spoken on the radio; nothing was listening for the clash. Indian radio adds a second layer:
English from the tower, and Hindi, Hinglish or Marathi from airside vehicles.

## What we built
Sentinel-V listens to tower, pilot and airside radio at Delhi, Mumbai and Pune. It keeps a live picture of which
aircraft holds which runway, checks that every pilot read the instruction back correctly, and **speaks a warning the
moment two clearances clash** — "Runway conflict, two niner right, Vistara niner two six." When a word was not heard
clearly, it asks the controller to confirm instead of guessing.

## How Gnani's models are used
| | Role in Sentinel-V |
|---|---|
| **Gnani Prisma v3.0** (speech-to-text) | Hears every call: Indian English for tower and pilots; Hindi, Marathi and Hinglish in one request for vehicles. Carries ATC keyterms ("niner", "tree", "hold short") and topic context. A second verbatim listen spells out numbers that come out glued ("290" for "two niner"). Median 0.49 s per call. |
| **Gnani Timbre v3.0 / v2.5** (text-to-speech) | Speaks the alert in a fixed voice, ready within 5 ms of the decision. It also voiced the whole test bench: 20+ voices in 4 languages, played through a simulated VHF radio. |

Between them sits a rule-based runway engine: the safety decision is never a guess, and the same words always give
the same verdict.

## Results (all measured)
- **0 of 90** deliberately wrong pilot readbacks missed in a locked exam on voices the system had never heard (frozen code, run once).
- **147 of 160** noisy-radio test scenarios caught on time (8 scenarios × 20 noise recordings at 10 dB).
- **0 of 558** calls shown as correct when they were not (locked exam, clean audio to 10 dB).
- Prisma hears a call in **0.49 s** (median); the spoken alert is ready **within 5 ms** after that.
- **17 experiments**, each with its pass/fail rule written before the result; failed ideas are published too.

## Why it matters
It adds a safety net without new hardware: one radio feed in, one spoken warning out. The same design (Gnani speech in,
deterministic rules, Gnani voice out) fits any voice-driven safety workflow: airside vehicles, ports, rail yards.

## Next
Human-voice testing (built in: `scripts/run_scenarios.py --human`), a surveillance feed so silent movements are seen too, and
more airports. Gnani Evon could write a plain-language summary of each alert for the shift log; it stays out of the
safety decision.

**Team:** Sanoer Soni (MIT World Peace University, Pune): speech pipeline, runway engine, experiments, site ·
Rudra Porwal: security runs, research. All audio is synthetic; no real ATC recordings
are used. Research prototype, not for operational use.
