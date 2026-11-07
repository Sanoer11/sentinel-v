'use client';
import { motion } from 'framer-motion';
import type { Summary } from '@/lib/types';

// How Sentinel-V uses Gnani's speech models. Every setting below is what gnani_client.py / sentinel_pipeline.py /
// sentinel_voice.py actually send; the numbers come from the measured runs (summary.json) or are stated with their source.

const FLOW = ['Radio call', 'Gnani Prisma v3.0', 'Runway engine', 'Gnani Timbre', 'Controller hears it'];

export default function GnaniModels({ summary }: { summary?: Summary }) {
  const s = summary?.stats;
  const prisma = [
    { t: 'Every call, three languages', d: 'Tower and pilot calls in Indian English (en-IN). Airside vehicle calls in one request with hi-IN, en-IN and mr-IN, so Hindi, Hinglish and Marathi are heard by the same listen.' },
    { t: 'Told it is listening to ATC', d: 'Each request carries ATC keyterms ("niner", "tree", "fife", "hold short", "cross runway", the airlines on frequency) and a topic line: an Indian airport tower frequency.' },
    { t: 'Two formats, used together', d: 'Transcribe gives digits the engine can check. When a number comes out glued ("290", "36053"), a verbatim listen of the same audio - already started in parallel - spells out what was said.' },
    { t: 'A hazard-word listen', d: 'A vehicle call nobody understood gets one more listen with hazard vocabulary (पक्षी, birds, FOD). It may add the bird report; it may never change which vehicle spoke.' },
  ];
  const timbre = [
    { t: 'The alert voice', d: 'One fixed Timbre v3.0 voice speaks the single most dangerous alert of a call: "Runway conflict, two niner right, Vistara niner two six." Its phrases are recorded once, so at alert time they are only joined - ready within 5 ms of the decision.' },
    { t: 'The whole test bench', d: 'Every tower, pilot and vehicle call in this project was spoken by Timbre: 20+ voices across v3.0 and v2.5, in English, Hindi, Hinglish and Marathi, then passed through a simulated VHF radio. No real ATC recording is used.' },
    { t: 'A held-back exam', d: 'A set of Timbre v2.5 voices was kept aside and used once, on frozen code, as the locked exam: 0 of 90 deliberately wrong readbacks missed.' },
  ];
  return (
    <section id="gnani" aria-labelledby="gnani-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Gnani models · how they are used</p>
        <h2 id="gnani-h" className="mt-2 text-3xl font-semibold tracking-tight">Built on Gnani&apos;s speech stack</h2>
        <p className="mt-2 max-w-3xl text-dim">
          Prisma is the ear and Timbre is the voice. Between them sits a rule-based runway engine, so the safety decision itself
          is never a guess: the same words always give the same verdict.
        </p>

        <ol aria-label="Path of one radio call" className="mt-8 flex flex-wrap items-center gap-2 p-0 font-mono text-[12px]">
          {FLOW.map((f, i) => (
            <li key={f} className="flex list-none items-center gap-2">
              <span className={`rounded-md border px-3 py-1.5 ${f.startsWith('Gnani') ? 'border-signal bg-signal/10 text-signal' : 'border-line bg-panel text-dim'}`}>{f}</span>
              {i < FLOW.length - 1 && <span aria-hidden="true" className="text-signal">→</span>}
            </li>
          ))}
        </ol>

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          {[
            { name: 'Gnani Prisma v3.0', role: 'speech-to-text · the ear', items: prisma,
              stat: s ? [`${s.calls} calls heard`, `median ${s.prisma_median?.toFixed(2)} s`, `90% within ${s.prisma_p90?.toFixed(2)} s`] : [] },
            { name: 'Gnani Timbre v3.0 + v2.5', role: 'text-to-speech · the voice', items: timbre,
              stat: ['alert ready < 5 ms', '20+ voices', '4 languages'] },
          ].map((m, k) => (
            <motion.article key={m.name} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '0px 0px -40px 0px' }} transition={{ delay: k * 0.1, duration: 0.5 }} className="card p-5">
              <p className="label">{m.role}</p>
              <h3 className="mt-1 text-xl font-semibold">{m.name}</h3>
              <div className="mt-3 flex flex-wrap gap-2 font-mono text-[11.5px]">
                {m.stat.map((x) => <span key={x} className="rounded border border-line bg-panel2 px-2 py-1 text-signal">{x}</span>)}
              </div>
              <ul className="mt-4 space-y-3 p-0">
                {m.items.map((it) => (
                  <li key={it.t} className="list-none">
                    <p className="font-medium">{it.t}</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-dim">{it.d}</p>
                  </li>
                ))}
              </ul>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
