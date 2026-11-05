'use client';
import { motion } from 'framer-motion';

const LIMITS = [
  { t: 'A clipped "Runway" is often gone from the audio', d: 'In 15 of 24 noisy readbacks it became a digit glued to the number ("227" for runway 27). Filling it in from the tower\'s call would hide a real wrong readback, so it stays AMBER: "runway not read back clearly".' },
  { t: '"Crossing" is lost in most noisy readbacks', d: '8 of 12 noisy clips (7 heard as "I think runway…"). A clipped "Holding" sounds the same, so no guess is made. A hold-short that is not confirmed on a busy runway is still RED.' },
  { t: 'A misheard callsign digit looks like a real pilot error', d: 'Prisma gives no confidence score, and a second listen mostly hears the same digits (A6). The alert ends with "confirm callsign" - the controller asks for a say-again, as ICAO requires anyway.' },
  { t: 'Synthetic voices, simulated radio', d: 'All speech is Gnani Timbre; the radio noise is simulated. Real friends\' recordings and a one-time locked exam on unseen voices are the next tests.' },
  { t: 'Hold times are assumptions', d: 'How long a landing or crossing "holds" a runway is a fixed number per action, not ATC data. A missing "runway vacated" keeps the runway busy - the RED says so.' },
  { t: 'Radio cannot see the ground', d: 'An aircraft that enters a runway without any call (an incursion with no radio) needs a surveillance feed. The engine has the slot for one; there is no data source here.' },
];

export default function Limits() {
  return (
    <section id="limits" aria-labelledby="limits-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Limits · measured, stated plainly</p>
        <h2 id="limits-h" className="mt-2 text-3xl font-semibold tracking-tight">What it cannot do (yet)</h2>
        <div className="mt-8 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
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
