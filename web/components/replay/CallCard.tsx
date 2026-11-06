'use client';
import { motion } from 'framer-motion';
import { memo } from 'react';
import type { Step } from '@/lib/types';

const CH = { tower: 'TOWER', pilot: 'PILOT', airside: 'VEHICLE' } as const;
const STATUS: Record<string, string> = {
  CONFIRMED: 'text-green', PROBABLE: 'text-amber', FLAGGED: 'text-red', REPORT: 'text-blue', '…': 'text-faint',
};
const ALERT = {
  RED: 'bg-red/15 text-text [&_b]:text-red', AMBER: 'bg-amber/15 text-text [&_b]:text-amber', INFO: 'bg-blue/10 text-text [&_b]:text-blue',
} as const;

/** Why the engine's callsign differs from the words on screen ("Tara, 926" -> VTI926). Only for a callsign
 *  found WITHOUT its airline word: Prisma's text is shown as heard, never rewritten. */
function readNote(step: Step): string | null {
  const n = (step.notes ?? []).find((x) => x.startsWith('callsign not in the usual airline+number form'));
  return n ? 'airline word not heard; matched by the flight number' : null;
}

/** One radio call: what Prisma heard (big), what was really said (small), the verdict and its alerts. */
function CallCard({ step, live, revealed }: { step: Step; live: boolean; revealed: boolean }) {
  const alerts = revealed ? step.alerts : [];
  const worst = alerts.some((a) => a.level === 'RED') ? 'border-l-red' : alerts.some((a) => a.level === 'AMBER') ? 'border-l-amber' : 'border-l-green';
  const extra = [
    step.heard2 && `second listen: ${step.heard2}`,
    step.hinted && 'heard with the hazard-word hint',
    step.latency != null && `heard in ${step.latency.toFixed(2)} s`,
  ].filter(Boolean).join(' · ');
  return (
    <motion.li layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
      className={`card list-none border-l-[3px] p-3.5 ${revealed ? worst : 'border-l-faint'} ${live ? 'ring-1 ring-signal' : ''}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-dim">
        <span>t+{step.t}s</span>
        <span className="font-semibold tracking-wider text-text">{CH[step.channel]}</span>
        <span>{step.speaker}</span>
        <span className={`ml-auto rounded border border-line px-1.5 py-0.5 text-[10.5px] ${STATUS[revealed ? step.status : '…'] ?? 'text-dim'}`}>
          {revealed ? step.status : 'listening…'}
        </span>
      </div>
      <p className="mt-2 font-mono text-[14px] leading-relaxed"><span className="sr-only">Heard: </span>{step.heard}</p>
      <p className="mt-1 text-[12px] text-dim"><span className="mr-1 font-mono text-[10.5px] tracking-wider text-faint">SAID</span>{step.said}</p>
      {revealed && extra && <p className="mt-1 font-mono text-[11.5px] text-dim">{extra}</p>}
      {revealed && step.read && readNote(step) && (
        <p className="mt-1 font-mono text-[11.5px] text-dim">
          <span className="mr-1.5 text-[10.5px] tracking-wider text-faint">READ AS</span>
          <span className="text-text">{step.read}</span>
          <span> · {readNote(step)}</span>
        </p>
      )}
      {alerts.map((a, i) => (
        <motion.p key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.06 * i }}
          className={`mt-2 rounded-md px-2.5 py-2 text-[12.5px] leading-snug ${ALERT[a.level]}`}>
          <b className="mr-1.5 font-mono text-[10.5px] tracking-wider">{a.level}</b>{a.text}
        </motion.p>
      ))}
    </motion.li>
  );
}

export default memo(CallCard);
