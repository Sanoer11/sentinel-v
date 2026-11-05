'use client';
import { motion } from 'framer-motion';
import { useMemo, useState } from 'react';
import { EXPERIMENTS, type ExpVerdict } from '@/lib/experiments';

const TONE: Record<ExpVerdict, string> = {
  PASS: 'bg-green/15 text-green', FAIL: 'bg-red/15 text-red', FINDING: 'bg-blue/15 text-blue',
  LIMIT: 'bg-amber/15 text-amber', NARROWED: 'bg-violet/15 text-violet',
};
const FILTERS: ('ALL' | ExpVerdict)[] = ['ALL', 'PASS', 'FAIL', 'FINDING', 'LIMIT', 'NARROWED'];

/** Searchable, sortable list of every experiment. Rows expand to show each fix's rule (fixed BEFORE the result). */
export default function Experiments() {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<'ALL' | ExpVerdict>('ALL');
  const [newest, setNewest] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    const r = EXPERIMENTS.filter((e) =>
      (filter === 'ALL' || e.parts.some((p) => p.verdict === filter)) &&
      (!t || [e.id, e.question, e.data, ...e.parts.flatMap((p) => [p.fix, p.rule, p.result])].join(' ').toLowerCase().includes(t)));
    return newest ? [...r].reverse() : r;
  }, [q, filter, newest]);
  const count = (v: ExpVerdict) => EXPERIMENTS.reduce((n, e) => n + e.parts.filter((p) => p.verdict === v).length, 0);

  return (
    <section id="experiments" aria-labelledby="exp-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Experiments · {EXPERIMENTS.length} runs, {count('PASS')} fixes shipped, {count('FAIL')} rejected</p>
        <h2 id="exp-h" className="mt-2 text-3xl font-semibold tracking-tight">Every fix had to pass a rule written before the result</h2>
        <p className="mt-2 max-w-3xl text-dim">
          A fix made after seeing the data it fixes always looks good on that data. So each idea got its rule first, then a run -
          usually on audio it had never heard. The rejected ones are listed too: they are why the shipped ones can be trusted.
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <label className="relative">
            <span className="sr-only">Search experiments</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: birds, niner, readback…"
              className="w-64 rounded-md border border-line bg-panel px-3 py-2 text-[13px] placeholder:text-faint" />
          </label>
          <div role="group" aria-label="Filter by verdict" className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
                className={`rounded-md border px-2.5 py-1.5 font-mono text-[11px] ${filter === f ? 'border-signal text-text' : 'border-line text-dim hover:text-text'}`}>
                {f}{f !== 'ALL' && ` ${count(f)}`}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setNewest((n) => !n)} aria-label={`Sort ${newest ? 'oldest' : 'newest'} first`}
            className="ml-auto rounded-md border border-line px-2.5 py-1.5 font-mono text-[11px] text-dim hover:text-text">
            {newest ? 'newest first ↓' : 'oldest first ↑'}
          </button>
        </div>

        <table className="mt-4 w-full border-collapse text-left text-[13px]">
          <thead>
            <tr className="label border-b border-line">
              <th scope="col" className="py-2 pr-3 font-normal">id</th>
              <th scope="col" className="hidden py-2 pr-3 font-normal sm:table-cell">date</th>
              <th scope="col" className="py-2 pr-3 font-normal">question</th>
              <th scope="col" className="py-2 font-normal">outcome</th>
            </tr>
          </thead>
          <tbody>
              {rows.map((e, i) => {
                const isOpen = open === e.id;
                return [
                  <motion.tr key={e.id} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0, transition: { delay: i * 0.025 } }}
                    className="cursor-pointer border-b border-line align-top hover:bg-panel"
                    onClick={() => setOpen(isOpen ? null : e.id)}>
                    <td className="py-3 pr-3 font-mono font-semibold">
                      <button type="button" aria-expanded={isOpen} aria-controls={`exp-${e.id}`} className="flex items-center gap-1.5"
                        onClick={(ev) => { ev.stopPropagation(); setOpen(isOpen ? null : e.id); }}>
                        <motion.span animate={{ rotate: isOpen ? 90 : 0 }} className="text-faint" aria-hidden="true">▸</motion.span>{e.id}
                      </button>
                    </td>
                    <td className="hidden whitespace-nowrap py-3 pr-3 font-mono text-[12px] text-dim sm:table-cell">{e.date}</td>
                    <td className="py-3 pr-3 leading-snug">{e.question}</td>
                    <td className="py-3">
                      <span className="flex flex-wrap gap-1">
                        {e.parts.map((p, k) => <span key={k} className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${TONE[p.verdict]}`}>{p.verdict}</span>)}
                      </span>
                    </td>
                  </motion.tr>,
                  isOpen && (
                    <tr key={`${e.id}-d`} id={`exp-${e.id}`} className="border-b border-line bg-panel2">
                      <td colSpan={4} className="p-0">
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} className="overflow-hidden">
                          <div className="grid gap-3 p-4">
                            <p className="font-mono text-[11.5px] text-dim">data: {e.data}</p>
                            {e.parts.map((p, k) => (
                              <div key={k} className="card p-3">
                                <p className="flex flex-wrap items-center gap-2 font-medium">
                                  <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${TONE[p.verdict]}`}>{p.verdict}</span>{p.fix}
                                </p>
                                <p className="mt-2 text-[12.5px]"><span className="label mr-2">rule, fixed first</span>{p.rule}</p>
                                <p className="mt-1 text-[12.5px]"><span className="label mr-2">result</span>{p.result}</p>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      </td>
                    </tr>
                  ),
                ];
              })}
          </tbody>
        </table>
        {rows.length === 0 && <p className="mt-4 text-dim">No experiment matches &ldquo;{q}&rdquo;.</p>}
      </div>
    </section>
  );
}
