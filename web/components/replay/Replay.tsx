'use client';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useRuns } from '@/lib/data';
import { runLabel, verdictTone } from '@/lib/format';
import type { Summary } from '@/lib/types';
import CallCard from './CallCard';
import RunwayMap from './RunwayMap';
import { usePlayer } from './usePlayer';

const TONE = { green: 'bg-green/15 text-green', amber: 'bg-amber/15 text-amber', red: 'bg-red/15 text-red' } as const;

export default function Replay({ summary, scenario, setScenario }: {
  summary?: Summary; scenario: string | null; setScenario: (id: string) => void;
}) {
  const runs = useRuns(scenario);
  const [runIdx, setRunIdx] = useState(0);
  const meta = summary?.scenarios.find((s) => s.id === scenario);

  // open on the clean-radio run (every scenario has one); the 20 noisy runs are one click away in the run menu
  useEffect(() => {
    if (!runs.data) return;
    const i = runs.data.findIndex((r) => r.cond === 'clean');
    setRunIdx(i < 0 ? 0 : i);
  }, [runs.data]);

  const run = runs.data?.[runIdx];
  const p = usePlayer(run);
  const current = run && p.shown >= 0 ? run.steps[p.shown] : null;
  const picture = run && p.revealed >= 0 ? run.steps[Math.min(p.revealed, p.shown)].picture : [];
  const shownAlerts = useMemo(() => {
    if (!run) return [];
    return run.steps.slice(0, p.revealed + 1).flatMap((s) => s.alerts.filter((a) => a.level !== 'INFO').map((a) => ({ ...a, t: s.t })));
  }, [run, p.revealed]);
  const geo = meta ? summary?.geo[meta.airport] : undefined;

  return (
    <section id="replay" aria-labelledby="replay-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Replay · saved runs, nothing re-heard</p>
        <h2 id="replay-h" className="mt-2 text-3xl font-semibold tracking-tight">Every call, as Prisma heard it</h2>
        <p className="mt-2 max-w-2xl text-dim">
          Pick a scenario and a run. Play gives each call&apos;s radio audio, then the engine&apos;s verdict, then the spoken alert.
          Big text is what Gnani Prisma heard; small text is what was really said.
        </p>

        <div className="mt-8 grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)_300px]">
          {/* scenario list */}
          <nav aria-label="Scenarios" className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
            {summary?.scenarios.map((s) => {
              const n = Object.values(s.counts.noisy).reduce((a, b) => a + (b ?? 0), 0);
              const on = s.counts.noisy['ON TIME'] ?? 0;
              return (
                <button key={s.id} type="button" onClick={() => setScenario(s.id)} aria-pressed={s.id === scenario}
                  className={`min-w-[180px] rounded-lg border p-3 text-left lg:min-w-0 ${s.id === scenario ? 'border-signal bg-panel' : 'border-line bg-panel2 hover:bg-panel'}`}>
                  <span className="flex items-center justify-between gap-2 font-mono text-[12.5px] font-semibold">
                    {s.id}
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${TONE[on === n ? 'green' : on ? 'amber' : 'red']}`}>{on}/{n}</span>
                  </span>
                  <span className="mt-1 block text-[12px] text-dim">{s.where}</span>
                </button>
              );
            })}
          </nav>

          {/* the run */}
          <div className="min-w-0">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-mono text-lg font-semibold">{scenario}</h3>
                <p className="mt-1 max-w-xl text-[13.5px] text-dim">{meta?.what}</p>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={p.playing ? p.stop : p.play} disabled={!run}
                  className="rounded-md bg-signal px-4 py-2 font-mono text-[12.5px] font-semibold text-ink disabled:opacity-40">
                  {p.playing ? '❚❚ Pause' : '▶ Play'}
                </button>
                <button type="button" onClick={p.step} disabled={!run || p.shown >= (run?.steps.length ?? 0) - 1}
                  className="rounded-md border border-line bg-panel px-3 py-2 font-mono text-[12.5px] disabled:opacity-40">Step</button>
                <button type="button" onClick={p.reset} disabled={!run}
                  className="rounded-md border border-line bg-panel px-3 py-2 font-mono text-[12.5px] disabled:opacity-40">Reset</button>
                <span className="w-16 text-right font-mono text-[12px] text-dim" aria-live="polite">{current ? `t = ${current.t} s` : 't = –'}</span>
              </div>
            </div>

            <label className="mt-4 flex flex-wrap items-center gap-2 text-[12.5px] text-dim">
              <span className="label">Run</span>
              <select value={runIdx} onChange={(e) => setRunIdx(+e.target.value)} disabled={!runs.data}
                className="rounded-md border border-line bg-panel px-2 py-1.5 font-mono text-[12.5px] text-text">
                {runs.data?.map((r, i) => <option key={i} value={i}>{runLabel(r.cond, r.seed)} - {r.verdict}</option>)}
              </select>
              {run && <span className={`rounded px-2 py-1 font-mono text-[10.5px] ${TONE[verdictTone(run.verdict)]}`}>{run.verdict}</span>}
            </label>

            <div className="card mt-4 p-3">
              <p className="label mb-1">{geo?.name} ({meta?.airport}) - who holds each runway</p>
              {geo && meta && <RunwayMap airport={meta.airport} strips={geo.strips} picture={picture} alerts={current && p.revealed === p.shown ? current.alerts : []} />}
              <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-dim" aria-label="Legend">
                <li><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-red align-[-1px]" />take-off / landing</li>
                <li><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-blue align-[-1px]" />crossing</li>
                <li><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-violet align-[-1px]" />line-up</li>
                <li><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-strip align-[-1px]" />free</li>
              </ul>
            </div>

            {runs.isError && <p role="alert" className="mt-4 text-red">Could not load this scenario ({String(runs.error)}). Refresh to retry.</p>}
            {runs.isLoading && <p className="mt-4 text-dim">Loading runs…</p>}
            <ol className="mt-4 flex flex-col gap-2.5 p-0" aria-label="Radio calls">
              {run?.steps.slice(0, p.shown + 1).map((s, i) => (
                <CallCard key={`${runIdx}-${i}`} step={s} live={i === p.shown && p.playing} revealed={i <= p.revealed} />
              ))}
            </ol>
            {run && p.shown < 0 && <p className="mt-2 text-[13px] text-faint">Press Play (with sound) or Step through the {run.steps.length} calls.</p>}
          </div>

          {/* alert side */}
          <aside aria-label="Alerts" className="flex flex-col gap-3">
            <div className={`card p-3.5 ${p.speaking ? 'border-red shadow-[0_0_28px_rgb(var(--red)/0.18)]' : ''}`} aria-live="assertive">
              <p className="label">Sentinel-V voice</p>
              <AnimatePresence mode="wait">
                <motion.p key={p.speaking ?? 'quiet'} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  className={`mt-2 font-mono ${p.speaking ? 'text-[15px] text-text' : 'text-[13px] text-faint'}`}>
                  {p.speaking ? <>🔊 &ldquo;{p.speaking}&rdquo;</> : 'quiet'}
                </motion.p>
              </AnimatePresence>
            </div>
            <p className="label mt-2">Alerts in this run</p>
            <ul className="m-0 flex flex-col gap-2 p-0">
              {shownAlerts.length === 0 && <li className="list-none text-[13px] text-faint">none yet</li>}
              {[...shownAlerts].reverse().map((a, i) => (
                <motion.li key={`${a.t}-${a.kind}-${i}`} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  className={`list-none rounded-md px-2.5 py-2 text-[12.5px] leading-snug ${a.level === 'RED' ? 'bg-red/15' : 'bg-amber/15'}`}>
                  <b className={`mr-1.5 font-mono text-[10.5px] ${a.level === 'RED' ? 'text-red' : 'text-amber'}`}>t+{a.t}s</b>{a.text}
                </motion.li>
              ))}
            </ul>
          </aside>
        </div>
      </div>
    </section>
  );
}
