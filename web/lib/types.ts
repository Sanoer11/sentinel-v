// Shapes of the files that scripts/export_web.py writes into public/data/. Kept in one place so the Python side and
// the site cannot drift apart silently: if a field changes, `npm run typecheck` fails in CI.

export type Level = 'RED' | 'AMBER' | 'INFO';
export type Verdict = 'ON TIME' | 'LATE' | 'OTHER-RED' | 'MISSED' | 'FALSE RED';
export type Channel = 'tower' | 'pilot' | 'airside';
export type Action = 'TAKEOFF' | 'LAND' | 'CROSS' | 'LINEUP' | 'STOPPED';

export interface Alert { level: Level; kind: string; text: string }
export interface Occupant { strip: string; cs: string; action: Action; rw: string; maybe?: string }  // maybe: runway heard glued, a guess (A14)

export interface Step {
  t: number;
  channel: Channel;
  speaker: string;
  said: string;          // the script (what was really spoken)
  heard: string;         // what Gnani Prisma v3.0 wrote
  heard2: string | null; // the verbatim second listen, when one was needed
  hinted: boolean;       // heard with the hazard-word hint (vehicle channel)
  status: string;
  latency: number | null;
  audio: string | null;
  spoken: { file: string | null; says: string } | null;
  alerts: Alert[];
  picture: Occupant[];   // who holds which runway after this call
  read?: string | null;  // the callsign the engine settled on
  notes?: string[];      // the engine's own notes on this call (e.g. matched by flight number)
}

export interface Run {
  scenario: string;
  cond: string;          // "clean" | "10" (dB)
  seed: number;          // which noise recording
  verdict: Verdict;
  false_red: boolean;
  steps: Step[];
}

export interface ScenarioMeta {
  id: string;
  where: string;
  what: string;
  airport: string;
  real: boolean;
  no_red: boolean;
  counts: Record<'clean' | 'noisy', Partial<Record<Verdict, number>>>;
}

export interface Summary {
  generated: string;
  git: string | null;
  stats: {
    noisy_runs: number;
    noisy_on_time: number;
    noisy_late: number;
    noise_samples: number;
    normal_runs: number;
    false_red: number;
    prisma_median: number | null;
    prisma_p90: number | null;
    alert_ready_median: number | null;
    calls: number;
  };
  latency: number[];
  readback: { wrong: Record<string, number>; correct: Record<string, number> };
  scenarios: ScenarioMeta[];
  geo: Record<string, { name: string; strips: string[]; cross: string[][] }>;
}
