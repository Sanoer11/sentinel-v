'use client';
import { motion } from 'framer-motion';

const STEPS = [
  { k: '01', t: 'Radio', d: 'Tower and pilot calls in Indian English; Bird Chaser and Follow Me vehicles in Hindi, Hinglish and Marathi. Push-to-talk clips, VHF static.' },
  { k: '02', t: 'Gnani Prisma v3.0', d: 'Transcribe every call. A glued number ("290", "36053") gets a second, verbatim listen of the same audio. A vehicle call nobody understood gets one hazard-word hint (पक्षी, birds, FOD) - it may add the bird word, never remove the vehicle.' },
  { k: '03', t: 'Parser', d: 'Callsign, runway and instruction from messy text: "niner", "tree", "fife", Devanagari digits, "29, right" with Prisma\'s comma. Nothing it is unsure of is shown as green.' },
  { k: '04', t: 'Runway engine', d: 'Keeps who holds each runway (Delhi\'s four, Mumbai\'s two crossing runways, Pune). Checks every readback against its clearance and every new clearance against the picture.' },
  { k: '05', t: 'Gnani Timbre voice', d: 'One alert per call, the most dangerous one: "Runway conflict, two niner right, Vistara niner two six". Phrases are pre-recorded, so the alert is ready within 5 ms of the decision.' },
];

export default function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">How it works</p>
        <h2 id="how-h" className="mt-2 text-3xl font-semibold tracking-tight">From a radio call to a spoken alert</h2>
        <ol className="mt-8 grid gap-3 p-0 md:grid-cols-5">
          {STEPS.map((s, i) => (
            <motion.li key={s.k} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '0px 0px -40px 0px' }}
              transition={{ delay: i * 0.1, duration: 0.5 }} className="card relative list-none p-4">
              <span className="font-mono text-[11px] text-signal">{s.k}</span>
              <p className="mt-1 font-semibold">{s.t}</p>
              <p className="mt-2 text-[12.5px] leading-relaxed text-dim">{s.d}</p>
              {i < STEPS.length - 1 && <span aria-hidden="true" className="absolute -right-2 top-1/2 hidden h-px w-4 bg-signal/60 md:block" />}
            </motion.li>
          ))}
        </ol>
        <p className="mt-6 max-w-3xl text-[13px] text-dim">
          This site is plain static files. It never calls Prisma or Timbre and holds no API key: every transcript and every
          audio clip on it was produced by the measured runs and saved, then replayed here exactly as recorded.
        </p>
      </div>
    </section>
  );
}
