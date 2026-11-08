// Every experiment run on Sentinel-V, with its rule written down BEFORE the result was seen.
// Failed ideas are listed on purpose: a fix that was measured and rejected is as much a result as one that shipped.
// Numbers are copied from each experiment's printed output (experiments/exp_a1.py ... experiments/exp_a17.py in the repo).

export type ExpVerdict = 'PASS' | 'FAIL' | 'FINDING' | 'LIMIT' | 'NARROWED';

export interface ExpPart {
  fix: string;
  rule: string;
  result: string;
  verdict: ExpVerdict;
}

export interface Experiment {
  id: string;
  date: string;
  question: string;
  data: string;
  parts: ExpPart[];
}

export const EXPERIMENTS: Experiment[] = [
  {
    id: 'A1', date: '30 Oct', data: '6 real recordings x 3 audio versions x 3 output styles = 54 calls',
    question: 'Before fixing anything: is "IFLY" lost because push-to-talk cuts the start, or because of noise? Are runway errors mishearing, or digits glued by the output step?',
    parts: [{
      fix: 'Find the cause', rule: 'Change one thing at a time; no fix before the cause is known.',
      result: 'The cut was not the main cause - the errors were mishearing. Transcribe stays the main listen; verbatim heard "two niner" where transcribe glued it into "290". 0 WRONG in 54 calls.',
      verdict: 'FINDING',
    }],
  },
  {
    id: 'A2', date: '30 Oct', data: '6 dev voices, 4 phrases, 2 audio versions, 2 styles (96 calls)',
    question: 'Two Step-0 fixes from A1: read "writer Bravo" as "right at Bravo" (Fix W), and re-hear a glued runway like "290" in verbatim (Fix G).',
    parts: [
      { fix: 'Fix W ("writer" = "right at")', rule: 'Shows up in 2+ voices AND never for "left at".', result: 'Seen in 0 of 6 synthetic voices (only in one human recording).', verdict: 'FAIL' },
      { fix: 'Fix G (verbatim second listen for a glued runway)', rule: 'Rescues 2+ voices AND the verbatim runway is never a real but wrong runway. Always AMBER.', result: 'Rescued 5 calls in 4 of 6 voices, 0 wrong. Live.', verdict: 'PASS' },
    ],
  },
  {
    id: 'A3', date: '31 Oct', data: 'Cached dev audio, ~15-20 clips',
    question: '"IFLY niner seven one four" came out as 90714: the same niner glue, inside a flight number (Fix N).',
    parts: [{ fix: 'Fix N', rule: 'Rescues 3+ different lines AND 0 WRONG.', result: '11 clips / 6 lines rescued, 0 WRONG. Live, always AMBER.', verdict: 'PASS' }],
  },
  {
    id: 'A4', date: '31 Oct', data: 'dev + dev2, 600 clips',
    question: 'Pilot readbacks lose the last digit in noise - is our squelch burst the cause? And: vehicles had no look-alike protection.',
    parts: [
      { fix: 'Squelch-tail trimmer', rule: 'Worth building only if removing the tail brings the full callsign back in 10+ of 19 clips.', result: '4 of 19. The cause is noise: the answer stays "callsign incomplete - say again".', verdict: 'FAIL' },
      { fix: 'Vehicle number double-check', rule: 'Catches every wrong vehicle AND leaves no more than 10% of right calls unconfirmed.', result: 'Caught the only wrong vehicle; 3 of 76 right calls not confirmed. Live.', verdict: 'PASS' },
    ],
  },
  {
    id: 'A5', date: '31 Oct', data: '129 flagged readbacks',
    question: 'Fill a readback\'s lost words from the tower\'s own call (Fix C)?',
    parts: [{ fix: 'Fix C (context fill)', rule: '0 WRONG, no deliberately wrong readback hidden, 10%+ rescued.', result: 'Rescued 39 of 129 (30%) - but 4 WRONG and 4 real wrong readbacks hidden. It is circular: it copies the tower and hides the pilot\'s error.', verdict: 'FAIL' }],
  },
  {
    id: 'A6', date: '1 Nov', data: '15 false REDs, 24 real catches',
    question: '15 correct readbacks got a RED "wrong callsign" because Prisma slipped a digit. Does a second listen of the same audio tell a slip from a real error?',
    parts: [{ fix: 'Second listen for callsign slips', rule: '1/3+ of false REDs fixed, at most 10% of real catches dropped, 0 wrong readbacks shown as a match.', result: '1 of 15 fixed. 12 of 15 heard the same wrong digits again: the noise is in the recording. Only a new transmission ("say again") is independent evidence.', verdict: 'FAIL' }],
  },
  {
    id: 'A7', date: '2-3 Nov', data: '44 clips where the runway was heard but its instruction was not',
    question: 'Can a verbatim second listen recover an instruction word ("Crossing", "Holding") that push-to-talk removed?',
    parts: [{ fix: 'Instruction second listen', rule: 'Right instruction in 20%+ of clips AND a wrong one in 0 (one invented "crossing" is never acceptable).', result: 'Right in 4 (9%), WRONG in 1.', verdict: 'FAIL' }],
  },
  {
    id: 'A8', date: '3 Nov', data: '124 vehicle clips, one Marathi voice',
    question: 'Marathi "पक्षी" (birds) was heard as "पक्की". Does a fixed hazard vocabulary hint (पक्षी, birds, FOD) bring it back?',
    parts: [{ fix: 'Hazard-word hint on every vehicle call', rule: 'Brings back 1/3+ of lost bird words, 0 false bird reports, no more lines worse than better.', result: '5 of 10 bird reports back, but 5 lines worse and one "पक्षी" inserted into a crossing request. Narrowed AFTER the run to calls listen 1 did not understand - so it needed new audio to count.', verdict: 'NARROWED' }],
  },
  {
    id: 'A9', date: '4 Nov', data: '6 new Marathi voices, 54 new lines x clean / 10 / 5 dB',
    question: 'Test the narrowed hint, and five mishearings each seen in only one voice ("Casa Air", "following", "Force", "writer", "379 or 2").',
    parts: [
      { fix: 'Hint v1', rule: '1/3+ back, 0 false birds, 0 lines made worse by the hint.', result: '9 of 11 back, 0 false birds - but 2 lines worse: it got the birds and lost the vehicle number listen 1 had.', verdict: 'FAIL' },
      { fix: 'Five word fixes', rule: 'Each must show up in 2+ new voices and make 0 of 1002 transcripts worse.', result: 'None appeared in 2+ new voices. Not added.', verdict: 'FAIL' },
    ],
  },
  {
    id: 'A10', date: '4 Nov', data: '24 new Marathi lines x 10 / 5 dB; 15 saved second listens',
    question: 'Hint v2: the hint may ADD the bird word but never remove the vehicle listen 1 heard. And: accept a second listen that heard no callsign.',
    parts: [
      { fix: 'Hint v2', rule: 'Same four rules as A9.', result: '3 lost, 2 back, 0 worse - 1 false bird. The double-check found it came from listen 1 itself ("4 birds is a 5" = "Bird Chaser 5"), not the hint: the rule had measured the wrong thing. Fixed the real cause instead (A11).', verdict: 'FAIL' },
      { fix: 'Fix G with a silent callsign', rule: '1+ better, 0 worse on every saved transcript.', result: '0 better, 0 worse. Off.', verdict: 'FAIL' },
    ],
  },
  {
    id: 'A11', date: '4 Nov', data: '30 new English lines x 3 noise levels + 295 saved transcripts; A10 re-heard',
    question: 'The English word "birds" fired on the station\'s own garbled name. Fix the cue, then re-run A10 under its unchanged rules.',
    parts: [
      { fix: 'Strict English bird cue', rule: '0 real birds lost, 0 false birds, half of English bird clips caught.', result: '385 transcripts: 0 lost, 0 false, 51 of 54 caught, +18 "bird activity" reports the old cue could not see. Live.', verdict: 'PASS' },
      { fix: 'Hint v2, re-run', rule: 'A10\'s rules, unchanged.', result: '3 lost, 2 back, 0 false, 0 worse. Live.', verdict: 'PASS' },
      { fix: 'Finding', rule: '-', result: 'The same audio heard twice gave a different text in 5 of 48 clips (1 changed the meaning).', verdict: 'FINDING' },
    ],
  },
  {
    id: 'A12', date: '4 Nov', data: '720 saved transcripts, 312 replayed scenario runs, new noise 5-14',
    question: 'DEL_2023 failed at 10 dB: the tower\'s runway was glued ("290") and the pilot\'s "Runway" was heard as "Taxiway".',
    parts: [
      { fix: 'Fix T ("taxiway N, cleared for takeoff" = runway)', rule: '1+ better, 0 worse; then on new noise 5-9.', result: '0 better (those lines had lost the callsign too); 0 changes on new noise. Off.', verdict: 'FAIL' },
      { fix: 'Fix L (the readback locates a lost runway)', rule: 'Readback check unchanged, 0 replays worse, 0 false RED; then new noise 10-14.', result: '0 of 75 wrong readbacks missed (unchanged), 0 of 312 replays worse; new noise: 4 better, 0 worse. Live.', verdict: 'PASS' },
      { fix: 'Fix V ("Vistara 9" cannot be VTI725)', rule: 'Same checks as Fix L.', result: 'Included in the new-noise check: 0 worse. Live.', verdict: 'PASS' },
    ],
  },
  {
    id: 'A13', date: '5 Nov', data: '6 voices x 7 lines that break x clean / 10 / 5 dB',
    question: 'Give every "seen in only one voice" problem a fair test.',
    parts: [
      { fix: '"Taxiway" / "One way" / "Airway" = Runway', rule: 'Starts a call in 2+ voices, 1+ better, 0 worse, 0 extra false RED.', result: '0, 1 and 0 voices. A lost "Runway" really becomes a digit glued to the number ("227" for 27) in 15 of 24 noisy readbacks.', verdict: 'FAIL' },
      { fix: '"vacate it" = vacated', rule: 'In 2+ voices, fewer false REDs, never more.', result: '0 voices. 3 of 18 "Runway vacated" were lost completely.', verdict: 'FAIL' },
      { fix: 'Misheard runway digit ("39" for 29)', rule: 'Stays on unless it makes anything worse.', result: '1 fresh case helped, 0 worse. Stays live.', verdict: 'PASS' },
      { fix: '"Crossing" clipped', rule: 'Report only - a clipped "Holding" sounds the same.', result: 'Lost in 8 of 12 noisy clips (7 as "I think runway..."). Still RED via "hold short not confirmed".', verdict: 'LIMIT' },
    ],
  },
{
    id: 'A14', date: '7 Nov', data: 'Every saved practice run (168) and readback transcript',
    question: 'Delhi 2023 at 10 dB: a take-off runway heard glued ("290, right") and lost in the readback never entered the runway picture, so the crossing looked safe.',
    parts: [
      { fix: 'Fix U (glued runway kept as a "maybe")', rule: 'Wrong readbacks missed stays 0, no new false RED, 0 runs worse, silent misses go down.', result: '4 of 6 silent Delhi misses became AMBER "possible runway conflict" at the right call; 0 worse. Live.', verdict: 'PASS' },
      { fix: 'Fix T ("Tara" = Vistara)', rule: 'Same rules.', result: '17 flags fewer, but 2 new false REDs. Off.', verdict: 'FAIL' },
    ],
  },
  {
    id: 'A15', date: '7 Nov', data: 'Every saved practice run and readback transcript',
    question: 'The airline word turned into digits in front of the flight number ("36053" for IFLY 6053).',
    parts: [
      { fix: 'Fix S (last digits = exactly one flight on frequency)', rule: '0 wrong readbacks missed, 0 runs worse, fewer flags.', result: '20 flags fewer, 0 worse. Always AMBER "confirm callsign". Live.', verdict: 'PASS' },
    ],
  },
  {
    id: 'A16', date: '7 Nov', data: '80 new practice runs with the exam voices (new noise 200-209) + all earlier practice',
    question: '"two niner right" heard as "29, arrived" by the exam\'s tower voice.',
    parts: [
      { fix: 'Fix R ("arrived" after a runway = right)', rule: '8+ calls from 2+ voices lose a flag, nothing worse.', result: 'Only 3 calls, one voice: the new voices rarely said "arrived". Off.', verdict: 'FAIL' },
    ],
  },
  {
    id: 'A17', date: '7 Nov', data: '248 practice runs (168 + 80 new) and 864 saved lines',
    question: 'Each remaining miss traced to one exact cause, counted on every saved transcript before any code.',
    parts: [
      { fix: 'Fix G ("runway 290, right" = 29R)', rule: '0 wrong readbacks missed, no new false RED, 0 runs worse, 1+ better.', result: 'First two digits right 61 of 61, side right 48 of 48. 13 runs better, 0 worse, 0 lines shown wrong. Steps back if the second listen disagrees. Live.', verdict: 'PASS' },
      { fix: 'Fix N ("Tara 9026" = VTI926)', rule: 'Same rules.', result: '"niner" written 90 inside a flight number, 10 of 10. 1 run better, 0 worse. Always AMBER. Live.', verdict: 'PASS' },
      { fix: 'Fix K (crossing a runway someone is taking off from)', rule: 'Same rules.', result: 'An aircraft cannot cross the runway it is departing from, so an unidentified crossing stays RED. 2 better, 0 worse. Live.', verdict: 'PASS' },
      { fix: 'Fix P ("clear for takeoff", "cleared to take off")', rule: 'Same rules.', result: 'The take-off was missing from the picture. 1 better, 0 worse. Live.', verdict: 'PASS' },
      { fix: 'Fix X (callsign lost, instruction trusted)', rule: 'Same rules.', result: 'Correct readbacks shown RED 15 -> 17: when the callsign is lost, the instruction is often garbled too. Off.', verdict: 'FAIL' },
      { fix: 'All four together', rule: 'Same rules.', result: 'Practice 10 dB on time 137 -> 147 of 160; exam voices 62 -> 70 of 80 (Delhi 2023 4 -> 9 of 10); false RED unchanged. Designed on this data, so not a held-out score.', verdict: 'PASS' },
    ],
  },
];
