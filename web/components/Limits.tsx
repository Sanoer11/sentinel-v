'use client';
import { motion } from 'framer-motion';

const LIMITS = [
  { t: 'Radio only', d: 'It hears what is said on frequency. An aircraft that moves without any call needs a surveillance feed; the engine has the slot for one, there is no data source here.' },
  { t: 'Synthetic voices, simulated radio', d: 'All speech is Gnani Timbre through a simulated VHF radio, by design: no real ATC recordings. The next test is human voices (run_scenarios.py --human).' },
  { t: 'A misheard callsign digit is treated as real', d: 'It cannot be told apart from a stranger taking a clearance, so it stays RED "confirm callsign" - 2 of 20 normal Delhi runs at 10 dB, 15 of 285 correct readbacks.' },
  { t: 'Clipped words are never guessed', d: 'When push-to-talk cuts "Runway" or "Crossing", the call stays AMBER instead of being filled in. A hold-short that is not confirmed on a busy runway is still RED.' },
];

export default function Limits() {
  return (
    <section id="limits" aria-labelledby="limits-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Scope · stated plainly</p>
        <h2 id="limits-h" className="mt-2 text-3xl font-semibold tracking-tight">Where it stops</h2>
        <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {LIMITS.map((l, i) => (
            <motion.div key={l.t} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              transition={{ delay: i * 0.06 }} className="card p-4">
              <p className="font-medium">{l.t}</p>
              <p className="mt-2 text-[12.5px] leading-relaxed text-dim">{l.d}</p>
            </motion.div>
          ))}
        </div>
        <p className="mt-6 text-[13px] text-dim">Decision support only. The controller decides.</p>
      </div>
    </section>
  );
}
