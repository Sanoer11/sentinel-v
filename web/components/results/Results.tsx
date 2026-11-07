'use client';
import { motion } from 'framer-motion';
import dynamic from 'next/dynamic';
import KpiCard from '../KpiCard';
import type { Summary } from '@/lib/types';

// charts are the heaviest code on the page: loaded only when this section is rendered, never on the server
const Loading = () => <div className="h-[300px] animate-pulse rounded-lg bg-panel2" />;
const OutcomeChart = dynamic(() => import('./OutcomeChart'), { ssr: false, loading: Loading });
const LatencyChart = dynamic(() => import('./LatencyChart'), { ssr: false, loading: Loading });
const ReadbackChart = dynamic(() => import('./ReadbackChart'), { ssr: false, loading: Loading });

export default function Results({ summary, onPick }: { summary?: Summary; onPick: (id: string) => void }) {
  const s = summary?.stats;
  const wrongTotal = summary ? Object.values(summary.readback.wrong).reduce((a, b) => a + b, 0) : 0;
  return (
    <section id="results" aria-labelledby="results-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Results · measured, not estimated</p>
        <h2 id="results-h" className="mt-2 text-3xl font-semibold tracking-tight">Measured on noisy radio</h2>
        <p className="mt-2 max-w-3xl text-dim">
          Each scenario was spoken by Timbre voices, passed through a simulated VHF radio at 10 dB signal-to-noise
          {s ? ` with ${s.noise_samples} different noise recordings` : ''}, heard by Prisma and judged by the engine.
          A run is on time only if every alert it must raise comes at the call it belongs to.
        </p>

        {s && summary && (
          <motion.div initial="hidden" whileInView="show" viewport={{ once: true, margin: '0px 0px -60px 0px' }}
            transition={{ staggerChildren: 0.08 }} className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="on time at 10 dB" value={s.noisy_on_time} suffix={` / ${s.noisy_runs}`} tone="green"
              detail={`8 scenarios x ${s.noise_samples} noise recordings: every expected alert at the call it belongs to`} />
            <KpiCard label="wrong readbacks missed" value={summary.readback.wrong.MATCH ?? 0} suffix={` / ${wrongTotal}`} tone="green"
              detail="deliberately wrong pilot readbacks, clean to 0 dB: every one flagged RED or AMBER" />
            <KpiCard label="locked exam, unseen voices" value={0} suffix=" / 90" tone="green"
              detail="wrong readbacks missed on frozen code, run once, voices kept aside until the end" />
            <KpiCard label="median hearing time" value={s.prisma_median ?? 0} decimals={2} suffix=" s" tone="signal"
              detail={`Prisma per call over ${s.calls} calls; 90% within ${s.prisma_p90?.toFixed(2) ?? '–'} s. The alert is ready within 5 ms after that.`} />
          </motion.div>
        )}

        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <figure className="card m-0 p-4">
            <figcaption className="mb-3">
              <p className="font-medium">Outcome of every 10 dB run</p>
              <p className="text-[12.5px] text-dim">Click a scenario to replay it.</p>
            </figcaption>
            {summary ? <OutcomeChart summary={summary} onPick={onPick} /> : <Loading />}
          </figure>
          <figure className="card m-0 p-4">
            <figcaption className="mb-3">
              <p className="font-medium">Time for Prisma to hear one call</p>
              <p className="text-[12.5px] text-dim">Seconds per radio call. Drag the bar underneath to zoom.</p>
            </figcaption>
            {summary ? <LatencyChart values={summary.latency} /> : <Loading />}
          </figure>
          <figure className="card m-0 p-4 lg:col-span-2">
            <figcaption className="mb-3">
              <p className="font-medium">Readback check: tower call + pilot readback, clean to 0 dB</p>
              <p className="text-[12.5px] text-dim">
                Top bar: deliberately wrong readbacks - every one flagged, none passed as a match. Bottom bar: correct readbacks;
                a RED there means a callsign digit was misheard, and the alert asks the controller to confirm.
              </p>
            </figcaption>
            {summary ? <ReadbackChart readback={summary.readback} /> : <Loading />}
          </figure>
        </div>
      </div>
    </section>
  );
}
