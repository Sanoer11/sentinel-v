# Sentinel-V — one-page pitch

**A second pair of ears for the control tower.** For tower controllers: it warns, the controller decides.
[Live site](https://sentinel-v-one.vercel.app) · [Demo video (3 min)](https://drive.google.com/file/d/1O7jVn8HPQsFjpHMvhrUyR6kl1Y9PoPkd/view) · [Short film](https://lnkd.in/p/ddndXZeH) · [Code](https://github.com/Sanoer11/sentinel-v)

## The problem
Runway safety in India still runs on voice. On 23 August 2023 at Delhi, one Vistara aircraft was cleared to cross
runway 29R while another was cleared to take off from it; a pilot noticed and the take-off was stopped. Nothing was
listening for the clash, and Indian radio mixes English with Hindi, Hinglish and Marathi.

## What we built
Sentinel-V listens to tower, pilot and airside radio at Delhi, Mumbai and Pune. It tracks who holds each runway,
checks every pilot readback, and **speaks a warning the moment two clearances clash**. When a word was not heard
clearly, it asks the controller to confirm instead of guessing. No new hardware: one radio feed in, one spoken
warning out.

## How Gnani's models are used
- **Gnani Prisma v3.0** (speech-to-text) hears every call: Indian English for tower and pilots; Hindi, Marathi and
  Hinglish in one request for vehicles, with ATC keyterms. A second verbatim listen spells out glued numbers
  ("290" for "two niner"). Median 0.49 s per call.
- **Gnani Timbre** (text-to-speech): v3.0 speaks the alert, ready within 5 ms of the decision, and the tower console's
  typed calls. v3.0 and v2.5 also voiced the test bench: about 20 voices in 4 languages.
- Between them sits a rule-based runway engine: the same words always give the same verdict.

## Results (all measured)
- **0 of 90** deliberately wrong readbacks missed in a locked exam on unheard voices (frozen code, run once).
- **147 of 160** noisy-radio scenario runs caught on time (practice set, 10 dB noise; locked exam: 27 of 40).
- **0 of 558** calls shown as correct when they were not (locked exam, clean audio to 10 dB).
- **17 experiments**, each rule written before its result; failed ideas are published too.

**Next:** human-voice testing, a surveillance feed for silent movements, more airports, and Gnani Evon for
plain-language alert summaries, kept out of the safety decision.

**Team:** Sanoer Soni (MIT World Peace University, Pune): speech pipeline, runway engine, experiments, site ·
Rudra Porwal: security runs, research. All audio is synthetic. Research prototype, not for operational use.
