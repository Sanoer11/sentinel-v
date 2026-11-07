'use client';
import { motion } from 'framer-motion';
import type { Summary } from '@/lib/types';
import AnimatedNumber from './AnimatedNumber';

const rise = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: 0.12 * i, duration: 0.6, ease: [0.16, 1, 0.3, 1] } }),
};

/** The Delhi 2023 picture in motion: one aircraft rolling for take-off, another told to cross the same runway. */
function RunwayScene() {
  const lights = Array.from({ length: 11 }, (_, i) => i);
  return (
    <svg viewBox="0 0 520 384" className="h-auto w-full" role="img"
      aria-label="Animated runway: an aircraft takes off while another is cleared to cross the same runway; Sentinel-V flags the conflict.">
      <defs>
        <linearGradient id="rw" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" style={{ stopColor: 'rgb(var(--strip))', stopOpacity: 0.15 }} />
          <stop offset="1" style={{ stopColor: 'rgb(var(--strip))', stopOpacity: 1 }} />
        </linearGradient>
        <radialGradient id="glow"><stop offset="0" style={{ stopColor: 'rgb(var(--red))', stopOpacity: 0.55 }} /><stop offset="1" style={{ stopColor: 'rgb(var(--red))', stopOpacity: 0 }} /></radialGradient>
      </defs>
      {/* runway in perspective */}
      <path d="M238 30 L282 30 L430 360 L90 360 Z" fill="url(#rw)" />
      {lights.map((i) => {
        const t = i / 10, y = 30 + t * 330, l = 238 - t * 148, r = 282 + t * 148;
        return (
          <g key={i}>
            <motion.circle cx={l - 4} cy={y} r={1.2 + t * 2.2} className="fill-amber"
              animate={{ opacity: [0.25, 1, 0.25] }} transition={{ duration: 2.4, repeat: Infinity, delay: (10 - i) * 0.12 }} />
            <motion.circle cx={r + 4} cy={y} r={1.2 + t * 2.2} className="fill-amber"
              animate={{ opacity: [0.25, 1, 0.25] }} transition={{ duration: 2.4, repeat: Infinity, delay: (10 - i) * 0.12 }} />
            {i % 2 === 0 && i < 10 && <rect x={259 - 0.6 - t * 1.6} y={y + 6} width={1.2 + t * 3.2} height={6 + t * 16} className="fill-text" opacity={0.35 + t * 0.4} />}
          </g>
        );
      })}
      {/* crossing taxiway */}
      <path d="M40 250 L480 250" className="stroke-strip" strokeWidth="14" opacity=".55" />
      {/* departing aircraft: rolls up the runway */}
      <motion.g initial={{ y: 0, scale: 1 }} animate={{ y: [0, -250], scale: [1, 0.35] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'easeIn', repeatDelay: 1 }} style={{ originX: '260px', originY: '336px' }}>
        <path d="M260 316 l7 22 l22 8 v6 l-22 -3 l-3 14 l7 5 v4 l-11 -3 l-11 3 v-4 l7 -5 l-3 -14 l-22 3 v-6 l22 -8 z" className="fill-text" />
      </motion.g>
      <text x="300" y="372" className="fill-text font-mono" fontSize="11">VTI725 · TAKE-OFF 29R</text>
      {/* crossing aircraft: creeps onto the runway */}
      <motion.g animate={{ x: [0, 118, 118, 0] }} transition={{ duration: 7, times: [0, 0.45, 0.85, 1], repeat: Infinity }}>
        <rect x="70" y="244" width="22" height="12" rx="6" className="fill-blue" />
        <text x="46" y="234" className="fill-blue font-mono" fontSize="11">VTI926 · CROSS 29R</text>
      </motion.g>
      {/* conflict pulse where they meet */}
      <motion.circle cx="259" cy="250" r="46" fill="url(#glow)" animate={{ opacity: [0, 0, 1, 0], scale: [0.6, 0.6, 1.15, 0.6] }}
        transition={{ duration: 7, times: [0, 0.4, 0.6, 1], repeat: Infinity }} />
      <motion.g animate={{ opacity: [0, 0, 1, 1, 0] }} transition={{ duration: 7, times: [0, 0.42, 0.5, 0.85, 1], repeat: Infinity }}>
        <rect x="286" y="150" width="226" height="42" rx="6" className="fill-red/15 stroke-red" />
        <text x="296" y="168" className="fill-red font-mono" fontSize="11" fontWeight="600">RED · RUNWAY CONFLICT 29R</text>
        <text x="296" y="183" className="fill-text font-mono" fontSize="10">&quot;Runway conflict, two niner right&quot;</text>
      </motion.g>
    </svg>
  );
}

/** Radio activity: bars that breathe like a live transmission. */
function Waveform() {
  return (
    <div className="flex h-10 items-end gap-[3px]" aria-hidden="true">
      {Array.from({ length: 48 }, (_, i) => (
        <motion.span key={i} className="w-[3px] rounded-sm bg-signal/70"
          animate={{ height: ['18%', `${30 + ((i * 37) % 70)}%`, '18%'] }}
          transition={{ duration: 1.1 + ((i * 13) % 9) / 10, repeat: Infinity, ease: 'easeInOut', delay: (i % 7) * 0.08 }} />
      ))}
    </div>
  );
}

export default function Hero({ summary, onReplay }: { summary?: Summary; onReplay: (id: string) => void }) {
  const s = summary?.stats;
  const stat = (n: number | undefined, d?: number, dec = 0) => (n === undefined ? '–' : <AnimatedNumber value={n} decimals={dec} />);
  return (
    <section id="top" className="relative overflow-hidden border-b border-line">
      <div className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{ backgroundImage: 'linear-gradient(rgb(var(--signal)) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--signal)) 1px, transparent 1px)', backgroundSize: '44px 44px' }} />
      <div className="relative mx-auto grid max-w-page items-center gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.1fr_1fr] md:py-20">
        <motion.div initial="hidden" animate="show">
          <motion.p custom={0} variants={rise} className="label">Gnani AI · Great Indian AI Internship Challenge</motion.p>
          <motion.h1 custom={1} variants={rise} className="mt-4 text-[34px] font-semibold leading-[1.12] tracking-tight sm:text-5xl">
            Hears the tower.<br />Watches the runway.<br /><span className="text-signal">Speaks before two clearances collide.</span>
          </motion.h1>
          <motion.p custom={2} variants={rise} className="mt-5 max-w-xl text-[15px] leading-relaxed text-dim">
            Sentinel-V listens to Indian ATC and airside radio - English tower calls, Hindi, Hinglish and Marathi vehicle
            calls - at Delhi, Mumbai and Pune. It keeps track of who holds each runway, checks every readback, and says the
            alert out loud. Speech-to-text by <b className="text-text">Gnani Prisma v3.0</b>, alert voice by <b className="text-text">Gnani Timbre</b>.
          </motion.p>
          <motion.div custom={3} variants={rise} className="mt-7 flex flex-wrap gap-3">
            <button type="button" onClick={() => onReplay('DEL_2023')}
              className="rounded-md bg-signal px-5 py-3 font-mono text-[13px] font-semibold text-ink hover:brightness-110">
              ▶ Replay Delhi, 23 Aug 2023
            </button>
            <a href="#results" className="rounded-md border border-line bg-panel px-5 py-3 font-mono text-[13px] hover:border-signal">
              Measured results
            </a>
          </motion.div>
          <motion.dl custom={4} variants={rise} className="mt-9 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
            {[
              { k: s ? <>{stat(s.noisy_on_time)}<span className="text-dim">/{s.noisy_runs}</span></> : '–', d: 'scenario runs on time at 10 dB radio noise' },
              { k: summary ? <>{stat(summary.readback.wrong.MATCH ?? 0)}<span className="text-dim">/{Object.values(summary.readback.wrong).reduce((a, b) => a + b, 0)}</span></> : '–', d: 'deliberately wrong readbacks missed' },
              { k: s?.prisma_median != null ? <>{stat(s.prisma_median, undefined, 2)}<span className="text-dim"> s</span></> : '–', d: 'median time for Prisma to hear a call' },
              { k: <>&lt;5<span className="text-dim"> ms</span></>, d: 'from a heard call to a spoken alert ready' },
            ].map((x, i) => (
              <div key={i}>
                <dt className="sr-only">{x.d}</dt>
                <dd className="m-0 font-mono text-2xl font-semibold">{x.k}</dd>
                <dd className="m-0 mt-1 text-[12px] leading-snug text-dim">{x.d}</dd>
              </div>
            ))}
          </motion.dl>
        </motion.div>
        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.9, delay: 0.2 }}
          className="card relative p-4">
          <p className="label mb-2">Delhi · 29R · what Sentinel-V sees</p>
          <RunwayScene />
          <div className="mt-2 flex items-center gap-3"><span className="label">radio</span><Waveform /></div>
        </motion.div>
      </div>
    </section>
  );
}
