'use client';
import { motion } from 'framer-motion';
import { memo } from 'react';
import AnimatedNumber from './AnimatedNumber';

export interface KpiCardProps {
  label: string;
  value: number;
  /** shown after the number, e.g. "/ 160" or " s" */
  suffix?: string;
  decimals?: number;
  detail: string;
  tone?: 'signal' | 'green' | 'amber' | 'red';
}

const TONE = { signal: 'text-signal', green: 'text-green', amber: 'text-amber', red: 'text-red' } as const;

export const cardVariants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.16, 1, 0.3, 1] } },
};

/** One measured number. The `detail` line says exactly what was measured - no number without its definition. */
function KpiCard({ label, value, suffix = '', decimals = 0, detail, tone = 'signal' }: KpiCardProps) {
  return (
    <motion.figure variants={cardVariants} whileHover={{ y: -3 }} className="card m-0 p-4" aria-label={`${label}: ${value.toFixed(decimals)}${suffix}`}>
      <figcaption className="label">{label}</figcaption>
      <p className={`mt-2 font-mono text-3xl font-semibold ${TONE[tone]}`}>
        <AnimatedNumber value={value} decimals={decimals} />
        <span className="text-xl text-dim">{suffix}</span>
      </p>
      <p className="mt-1 text-[12.5px] leading-snug text-dim">{detail}</p>
    </motion.figure>
  );
}

export default memo(KpiCard);
