import type { Verdict, Level } from './types';

/** Tailwind colour token for a scenario verdict. Colour is never the only signal: the verdict text is always shown. */
export function verdictTone(v: Verdict): 'green' | 'amber' | 'red' {
  if (v === 'ON TIME') return 'green';
  if (v === 'LATE' || v === 'OTHER-RED') return 'amber';
  return 'red';
}

export function levelTone(l: Level): 'red' | 'amber' | 'blue' {
  return l === 'RED' ? 'red' : l === 'AMBER' ? 'amber' : 'blue';
}

export function runLabel(cond: string, seed: number): string {
  return cond === 'clean' ? 'clean audio' : `${cond} dB · noise ${seed}`;
}

/** "137 / 160" style, and a percent that is honest about tiny denominators. */
export function ratio(n: number, d: number): string {
  return d ? `${n} / ${d}` : '–';
}

export function pct(n: number, d: number): string {
  return d ? `${Math.round((100 * n) / d)}%` : '–';
}

/** Histogram of seconds into fixed-width bins, for the latency chart. */
export function histogram(values: number[], width = 0.1, max = 2.5): { bin: number; label: string; count: number }[] {
  const n = Math.ceil(max / width);
  const bins = Array.from({ length: n + 1 }, (_, i) => ({
    bin: +(i * width).toFixed(2),
    label: i === n ? `≥${max.toFixed(1)}` : (i * width).toFixed(1),
    count: 0,
  }));
  for (const v of values) bins[Math.min(n, Math.floor(v / width))].count += 1;
  return bins;
}
