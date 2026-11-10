'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import RunwayMap from '@/components/replay/RunwayMap';
import type { Alert, Occupant, Summary } from '@/lib/types';
import { loadEngine, toCallsign, type Engine, type EngineAlert, type Hold } from './engine';
import { play, prisma, startRecording, timbre } from './radio';

type Channel = 'tower' | 'pilot' | 'airside';
type Source = 'typed' | 'radio' | 'mic';
interface LogRow { id: number; t: number; channel: Channel; text: string; status: string; read: string | null; notes: string[]; alerts: EngineAlert[]; src: Source; voiced: boolean }
interface AlertRow extends EngineAlert { id: number; t: number; ack: boolean }

const CH: { id: Channel; label: string }[] = [{ id: 'tower', label: 'Tower' }, { id: 'pilot', label: 'Pilot' }, { id: 'airside', label: 'Vehicle' }];
const STATUS: Record<string, string> = { CONFIRMED: 'text-green', PROBABLE: 'text-amber', FLAGGED: 'text-red', REPORT: 'text-blue' };
const PRESET: Record<string, { traffic: string[]; example: string; scenario: string; calls: [Channel, string][] }> = {
  VIDP: {
    traffic: ['VTI725', 'VTI926', 'AIC2817', 'IGO5134', 'IGO5124'], example: 'Delhi, 23 Aug 2023', scenario: 'DEL_2023',
    calls: [['tower', 'Vistara 725, runway 29 right, cleared for takeoff'], ['pilot', 'Runway 29 right, cleared for takeoff, Vistara 725'],
      ['tower', 'Vistara 926, cross runway 29 right']],
  },
  VABB: {
    traffic: ['AIC657', 'IGO6053', 'AKJ1123', 'BIRDCHASER2'], example: 'Birds on the runway (Marathi)', scenario: 'BIRDS_MR',
    calls: [['tower', 'Air India 657, runway 27, cleared for takeoff'], ['pilot', 'Runway 27, cleared for takeoff, Air India 657'],
      ['airside', 'Tower, Bird Chaser 2, runway 27 वर पक्षी आहेत']],
  },
  VAPO: {
    traffic: ['AKJ2612', 'AIC947'], example: 'Stop immediately, Pune', scenario: 'STOP',
    calls: [['tower', 'Akasa Air 2612, runway 10, cleared for takeoff'], ['pilot', 'Runway 10, cleared for takeoff, Akasa Air 2612'],
      ['tower', 'Air India 947, hold short runway 10'], ['pilot', 'Crossing runway 10, Air India 947']],
  },
};
const clock = (t: number) => `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const VOICE = '/audio/voice/';
const csv = (v: string) => `"${v.replace(/"/g, '""')}"`;

/** A working console on the real rule engine: typed calls in, runway board, alerts to acknowledge, shift log out. */
export default function TowerConsole({ summary }: { summary?: Summary }) {
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [error, setError] = useState('');
  const [airport, setAirport] = useState('VIDP');
  const [traffic, setTraffic] = useState<string[]>(PRESET.VIDP.traffic);
  const [channel, setChannel] = useState<Channel>('tower');
  const [text, setText] = useState('');
  const [add, setAdd] = useState('');
  const [addErr, setAddErr] = useState(false);
  const [now, setNow] = useState(0);
  const [holds, setHolds] = useState<Hold[]>([]);
  const [log, setLog] = useState<LogRow[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const eng = useRef<Engine | null>(null);
  const t0 = useRef(0);
  const seq = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clips = useRef<Record<string, string>>({});
  const voice = useRef<{ token: number; audio: HTMLAudioElement | null; busy: boolean }>({ token: 0, audio: null, busy: false });
  const [said, setSaid] = useState<{ text: string; live: boolean; missing: boolean } | null>(null);
  // the radio: one transmission at a time, like a real frequency
  const radioQ = useRef<Promise<void>>(Promise.resolve());
  const shift = useRef(0);
  const radioAudio = useRef<HTMLAudioElement | null>(null);
  const [onAir, setOnAir] = useState<{ channel: Channel; text: string; how: string } | null>(null);
  const [liveVoice, setLiveVoice] = useState<{ on: boolean; note: string }>({ on: true, note: '' });
  const [mic, setMic] = useState<{ state: 'idle' | 'rec' | 'hearing'; note: string }>({ state: 'idle', note: '' });
  const recRef = useRef<{ stop: () => Promise<Blob> } | null>(null);

  /** Speak one alert by playing its recorded Timbre phrase clips in order (headline, where, who). */
  const speak = useCallback((phrases: string[] | null) => {
    if (!phrases) return;
    const v = voice.current;
    v.audio?.pause();
    const token = ++v.token;
    const text = phrases.join(', ');
    const files = phrases.map((p) => clips.current[p]);
    if (files.some((f) => !f)) { v.busy = false; setSaid({ text, live: false, missing: true }); return; }
    v.busy = true;
    setSaid({ text, live: true, missing: false });
    const next = (i: number) => {
      if (token !== v.token) return;
      if (i >= files.length) { v.busy = false; setSaid({ text, live: false, missing: false }); return; }
      const a = new Audio(VOICE + files[i]);
      v.audio = a;
      const on = () => timers.current.push(setTimeout(() => next(i + 1), i === 0 ? 250 : 120));
      a.onended = on; a.onerror = on;
      a.play().catch(on);
    };
    next(0);
  }, []);
  const hush = useCallback(() => { voice.current.token++; voice.current.busy = false; voice.current.audio?.pause(); setSaid(null); }, []);

  const elapsed = () => Math.round((Date.now() - t0.current) / 100) / 10;
  const raise = useCallback((t: number, list: EngineAlert[]) => {
    const rows = list.filter((a) => a.level !== 'INFO').map((a) => ({ ...a, id: ++seq.current, t, ack: false }));
    if (rows.length) setAlerts((old) => [...rows.reverse(), ...old]);
  }, []);

  const begin = useCallback((ap: string, tr: string[]) => {
    timers.current.forEach(clearTimeout); timers.current = [];
    shift.current++; radioQ.current = Promise.resolve(); radioAudio.current?.pause(); setOnAir(null);
    eng.current?.start(ap, tr);
    t0.current = Date.now();
    hush();
    setNow(0); setHolds([]); setLog([]); setAlerts([]);
  }, [hush]);

  const start = async () => {
    setPhase('loading');
    try {
      eng.current = await loadEngine();
      clips.current = await fetch(`${VOICE}index.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
      begin(airport, traffic);
      setPhase('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('error');
    }
  };

  // one tick a second: holds count down and expire, overdue readbacks raise their alert
  useEffect(() => {
    if (phase !== 'ready') return;
    const id = setInterval(() => {
      const t = elapsed();
      const r = eng.current!.tick(t);
      setNow(t); setHolds(r.picture); raise(t, r.alerts); speak(r.spoken);
    }, 1000);
    return () => clearInterval(id);
  }, [phase, raise, speak]);
  useEffect(() => () => { timers.current.forEach(clearTimeout); voice.current.token++; voice.current.audio?.pause(); }, []);

  const send = useCallback((ch: Channel, said: string, src: Source = 'typed', voiced = false) => {
    const words = said.trim();
    if (!words || !eng.current) return;
    const t = elapsed();
    const r = eng.current.call(t, ch, words);
    setNow(t); setHolds(r.picture); raise(t, r.alerts); speak(r.spoken);
    setLog((old) => [{ id: ++seq.current, t, channel: ch, text: words, status: r.status, read: r.read, notes: r.notes, alerts: r.alerts, src, voiced }, ...old]);
  }, [raise, speak]);

  /** Put one transmission on the radio: play it, then the engine reads it (as the system does once a call is heard). */
  const onRadio = useCallback((job: (alive: () => boolean) => Promise<void>) => {
    const mine = shift.current;
    const alive = () => mine === shift.current;
    const quiet = async () => { for (let i = 0; i < 100 && voice.current.busy && alive(); i++) await new Promise((r) => setTimeout(r, 150)); };
    radioQ.current = radioQ.current.then(quiet).then(() => (alive() ? job(alive) : undefined)).catch(() => undefined);
  }, []);

  /** A typed call: Gnani Timbre speaks it in the voice of whoever is talking, then the engine checks it. */
  const transmit = useCallback((ch: Channel, words: string) => {
    const w = words.trim();
    if (!w) return;
    onRadio(async (alive) => {
      let voiced = false;
      if (liveVoice.on) {
        setOnAir({ channel: ch, text: w, how: 'Gnani Timbre is speaking it…' });
        const r = await timbre(w, ch);
        if (!alive()) return;
        if ('url' in r) {
          setOnAir({ channel: ch, text: w, how: 'spoken by Gnani Timbre' });
          await play(r.url, (a) => { radioAudio.current = a; });
          URL.revokeObjectURL(r.url);
          voiced = true;
        } else {
          setLiveVoice({ on: r.status !== 503, note: r.status === 503 ? 'Live voice is not set up on this server.' : `Live voice paused: ${r.error}.` });
        }
      }
      if (!alive()) return;
      setOnAir(null);
      send(ch, w, 'typed', voiced);
    });
  }, [liveVoice.on, onRadio, send]);

  /** Speak a call into the microphone: Gnani Prisma hears it, then the engine checks what Prisma heard. */
  const toggleMic = async () => {
    if (mic.state === 'rec') {
      const rec = recRef.current; recRef.current = null;
      if (!rec) return;
      setMic({ state: 'hearing', note: 'Gnani Prisma is listening…' });
      try {
        const wav = await rec.stop();
        const r = await prisma(wav, channel);
        if ('text' in r && r.text) {
          setMic({ state: 'idle', note: `Gnani Prisma heard it in ${r.seconds.toFixed(2)} s.` });
          onRadio(async () => { send(channel, r.text, 'mic', true); });
        } else {
          setMic({ state: 'idle', note: 'text' in r ? 'Prisma heard no words - try again, a little louder.' : `Could not reach Prisma (${r.error}).` });
        }
      } catch {
        setMic({ state: 'idle', note: 'The recording could not be read.' });
      }
      return;
    }
    try {
      recRef.current = await startRecording(12, () => void toggleMicRef.current?.());
      setMic({ state: 'rec', note: 'Recording - speak the call, then press stop (12 s max).' });
    } catch {
      setMic({ state: 'idle', note: 'Microphone not allowed in this browser.' });
    }
  };
  const toggleMicRef = useRef<(() => Promise<void>) | null>(null);
  toggleMicRef.current = toggleMic;

  const pickAirport = (ap: string) => {
    setAirport(ap); setTraffic(PRESET[ap].traffic);
    if (phase === 'ready') begin(ap, PRESET[ap].traffic);
  };
  const changeTraffic = (next: string[]) => { setTraffic(next); eng.current?.setTraffic(next); };
  const addFlight = () => {
    const cs = toCallsign(add);
    if (!cs) { setAddErr(true); return; }
    setAddErr(false); setAdd('');
    if (!traffic.includes(cs)) changeTraffic([...traffic, cs]);
  };
  const example = async () => {
    begin(airport, traffic);
    const p = PRESET[airport];
    type Step = { channel: Channel; heard: string; audio: string | null };
    const runs: { cond: string; steps: Step[] }[] | null = await fetch(`/data/runs/${p.scenario}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const steps = runs?.find((r) => r.cond === 'clean')?.steps;
    if (!steps) { p.calls.forEach(([ch, w]) => transmit(ch, w)); return; }
    steps.forEach((s) => onRadio(async (alive) => {
      if (s.audio) {
        setOnAir({ channel: s.channel, text: s.heard, how: 'recorded radio (Gnani Timbre voice), as Gnani Prisma heard it' });
        await play(`/${s.audio}`, (a) => { radioAudio.current = a; });
      }
      if (!alive()) return;
      setOnAir(null);
      send(s.channel, s.heard, 'radio', Boolean(s.audio));
      await new Promise((r) => setTimeout(r, 350));
    }));
  };
  const download = () => {
    const rows = [['time_s', 'channel', 'call', 'status', 'read_as', 'alerts'].join(',')]
      .concat([...log].reverse().map((r) => [r.t.toFixed(1), r.channel, csv(r.text), r.status, r.read ?? '',
        csv(r.alerts.map((a) => `${a.level} ${a.text}`).join(' | '))].join(',')));
    const url = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = `sentinel-v-shift-log-${airport}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const geo = summary?.geo[airport];
  const open = alerts.filter((a) => !a.ack);
  const ready = phase === 'ready';

  return (
    <section id="console" aria-labelledby="console-h" className="border-b border-line">
      <div className="mx-auto max-w-page px-4 py-14 sm:px-6">
        <p className="label">Tower console · the real rule engine, running in your browser</p>
        <h2 id="console-h" className="mt-2 text-3xl font-semibold tracking-tight">Type a call. Watch the runways.</h2>
        <p className="mt-2 max-w-2xl text-dim">
          What a controller would keep open: calls come in, the board shows who holds each runway and for how long, alerts wait to be
          acknowledged, RED alerts are spoken, and the shift log downloads. A typed call is spoken on the radio by Gnani Timbre, then
          checked; press the mic and Gnani Prisma hears your own call. The examples play real recorded radio, as Prisma heard it.
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-[12.5px] text-dim">
            <span className="label">Airport</span>
            <select value={airport} onChange={(e) => pickAirport(e.target.value)}
              className="rounded-md border border-line bg-panel px-2 py-1.5 font-mono text-[12.5px] text-text">
              {Object.keys(PRESET).map((ap) => <option key={ap} value={ap}>{summary?.geo[ap]?.name ?? ap} ({ap})</option>)}
            </select>
          </label>
          {!ready ? (
            <button type="button" onClick={start} disabled={phase === 'loading'}
              className="rounded-md bg-signal px-4 py-2 font-mono text-[12.5px] font-semibold text-ink disabled:opacity-60">
              {phase === 'loading' ? 'Loading the engine…' : 'Start the console'}
            </button>
          ) : (
            <>
              <button type="button" onClick={example} className="rounded-md bg-signal px-4 py-2 font-mono text-[12.5px] font-semibold text-ink">
                ▶ Example: {PRESET[airport].example}
              </button>
              <button type="button" onClick={() => begin(airport, traffic)} className="rounded-md border border-line bg-panel px-3 py-2 font-mono text-[12.5px]">
                New shift
              </button>
              <span className="font-mono text-[12px] text-dim" aria-live="off">shift time {clock(now)}</span>
            </>
          )}
          {phase === 'idle' && <span className="text-[12.5px] text-faint">Loads the Python engine once (about 10 MB).</span>}
        </div>
        {phase === 'error' && (
          <p role="alert" className="mt-3 text-[13px] text-red">The console could not start ({error}). The rest of the site is not affected; try again on a better connection.</p>
        )}

        <div className={`mt-6 grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)_300px] ${ready ? '' : 'pointer-events-none opacity-40'}`} aria-hidden={!ready}>
          {/* who is on frequency */}
          <div>
            <p className="label">On frequency</p>
            <ul className="m-0 mt-2 flex flex-wrap gap-1.5 p-0 lg:flex-col">
              {traffic.map((cs) => (
                <li key={cs} className="flex list-none items-center justify-between gap-2 rounded-md border border-line bg-panel2 px-2.5 py-1.5 font-mono text-[12.5px]">
                  {cs}
                  <button type="button" aria-label={`Remove ${cs}`} onClick={() => changeTraffic(traffic.filter((x) => x !== cs))} className="text-faint hover:text-red">×</button>
                </li>
              ))}
            </ul>
            <form className="mt-2 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); addFlight(); }}>
              <input value={add} onChange={(e) => { setAdd(e.target.value); setAddErr(false); }} placeholder="IFLY 512" aria-label="Add a flight or vehicle"
                className={`min-w-0 flex-1 rounded-md border bg-panel px-2 py-1.5 font-mono text-[12.5px] ${addErr ? 'border-red' : 'border-line'}`} />
              <button type="submit" className="rounded-md border border-line bg-panel px-2.5 py-1.5 font-mono text-[12.5px]">Add</button>
            </form>
            <p className={`mt-1.5 text-[11.5px] ${addErr ? 'text-red' : 'text-faint'}`}>
              IFLY, Air India, Vistara, Akasa Air, Follow Me or Bird Chaser, then the number. A callsign that is not on this list is flagged.
            </p>
          </div>

          {/* calls in, board, log */}
          <div className="min-w-0">
            <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); transmit(channel, text); setText(''); }}>
              <div role="group" aria-label="Who is speaking" className="flex overflow-hidden rounded-md border border-line">
                {CH.map((c) => (
                  <button key={c.id} type="button" aria-pressed={channel === c.id} onClick={() => setChannel(c.id)}
                    className={`px-3 py-2 font-mono text-[12.5px] ${channel === c.id ? 'bg-signal font-semibold text-ink' : 'bg-panel text-dim'}`}>{c.label}</button>
                ))}
              </div>
              <input value={text} onChange={(e) => setText(e.target.value)} aria-label="The radio call, as heard"
                placeholder={channel === 'tower' ? 'Vistara 725, runway 29 right, cleared for takeoff' : channel === 'pilot' ? 'Runway 29 right, cleared for takeoff, Vistara 725' : 'Tower, Bird Chaser 2, birds on runway 27'}
                className="min-w-[220px] flex-1 rounded-md border border-line bg-panel px-3 py-2 font-mono text-[13px]" />
              <button type="submit" disabled={!text.trim()} className="rounded-md bg-signal px-4 py-2 font-mono text-[12.5px] font-semibold text-ink disabled:opacity-40">Send</button>
              <button type="button" onClick={toggleMic} disabled={mic.state === 'hearing'} aria-pressed={mic.state === 'rec'}
                className={`rounded-md border px-3 py-2 font-mono text-[12.5px] disabled:opacity-50 ${mic.state === 'rec' ? 'border-red bg-red/15 text-red' : 'border-line bg-panel text-text'}`}>
                {mic.state === 'rec' ? '■ Stop' : '🎙 Speak'}
              </button>
            </form>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-faint">
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={liveVoice.on} onChange={(e) => setLiveVoice({ on: e.target.checked, note: '' })} />
                Speak typed calls with Gnani Timbre
              </label>
              {liveVoice.note && <span>{liveVoice.note}</span>}
              {mic.note && <span aria-live="polite">{mic.note}</span>}
            </div>
            <div className={`mt-3 flex items-center gap-3 rounded-md border px-3 py-2 font-mono text-[12.5px] ${onAir ? 'border-signal bg-signal/10' : 'border-line bg-panel2'}`} aria-live="polite">
              <span className={`inline-block h-2 w-2 rounded-full ${onAir ? 'animate-pulse bg-signal' : 'bg-line'}`} aria-hidden="true" />
              {onAir ? (
                <span className="min-w-0"><b className="mr-2 tracking-wider">{CH.find((c) => c.id === onAir.channel)?.label.toUpperCase()}</b>
                  <span className="text-text">{onAir.text}</span><span className="ml-2 text-[11px] text-dim">· {onAir.how}</span></span>
              ) : <span className="text-faint">frequency quiet</span>}
            </div>

            <div className="card mt-4 p-3">
              <p className="label mb-1">{geo?.name} ({airport}) - who holds each runway now</p>
              {geo && <RunwayMap airport={airport} strips={geo.strips} picture={holds as unknown as Occupant[]} alerts={open as Alert[]} />}
              {holds.length === 0 ? <p className="mt-1 text-[12.5px] text-faint">All runways free.</p> : (
                <ul className="m-0 mt-1 flex flex-wrap gap-x-5 gap-y-1 p-0 font-mono text-[12px] text-dim" aria-label="Runway holds">
                  {holds.map((h) => (
                    <li key={h.cs + h.action + h.rw} className="list-none">
                      <span className="text-text">{h.cs.startsWith('UNIDENTIFIED') ? 'unidentified' : h.cs}</span> {h.action} {h.rw} · {h.left} s left
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <ol className="m-0 mt-4 flex flex-col gap-2 p-0" aria-label="Calls this shift, newest first">
              {log.length === 0 && <li className="list-none text-[13px] text-faint">No calls yet. Type one above, or play the example.</li>}
              {log.map((r) => {
                const worst = r.alerts.some((a) => a.level === 'RED') ? 'border-l-red' : r.alerts.some((a) => a.level === 'AMBER') ? 'border-l-amber' : 'border-l-green';
                return (
                  <li key={r.id} className={`card list-none border-l-[3px] p-3 ${worst}`}>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-dim">
                      <span>{clock(r.t)}</span>
                      <span className="font-semibold tracking-wider text-text">{CH.find((c) => c.id === r.channel)?.label.toUpperCase()}</span>
                      <span>{r.src === 'mic' ? 'your voice · heard by Gnani Prisma' : r.src === 'radio' ? 'recorded radio · as Prisma heard it' : r.voiced ? 'typed · spoken by Gnani Timbre' : 'typed'}</span>
                      {r.read && <span>read as {r.read}</span>}
                      <span className={`ml-auto rounded border border-line px-1.5 py-0.5 text-[10.5px] ${STATUS[r.status] ?? 'text-dim'}`}>{r.status}</span>
                    </div>
                    <p className="mt-1.5 font-mono text-[13.5px] leading-relaxed">{r.text}</p>
                    {r.notes.length > 0 && <p className="mt-1 text-[12px] text-dim">{r.notes.join(' · ')}</p>}
                    {r.alerts.filter((a) => a.level !== 'INFO').map((a, i) => (
                      <p key={i} className={`mt-2 rounded-md px-2.5 py-1.5 text-[12.5px] leading-snug ${a.level === 'RED' ? 'bg-red/15' : 'bg-amber/15'}`}>
                        <b className={`mr-1.5 font-mono text-[10.5px] tracking-wider ${a.level === 'RED' ? 'text-red' : 'text-amber'}`}>{a.level}</b>{a.text}
                      </p>
                    ))}
                  </li>
                );
              })}
            </ol>
          </div>

          {/* alerts to act on */}
          <aside aria-label="Alerts to acknowledge" className="flex flex-col gap-2">
            <div className={`card mb-1 p-3.5 ${said?.live ? 'border-red shadow-[0_0_28px_rgb(var(--red)/0.18)]' : ''}`} aria-live="assertive">
              <p className="label">Sentinel-V voice</p>
              <p className={`mt-2 font-mono ${said?.live ? 'text-[15px] text-text' : 'text-[13px] text-faint'}`}>
                {said ? <>{said.live ? '🔊 ' : ''}&ldquo;{said.text}&rdquo;</> : 'quiet'}
              </p>
              {said?.missing && <p className="mt-1.5 text-[11.5px] text-faint">Not spoken: no clip is recorded for this aircraft. Clips are recorded ahead for the expected traffic.</p>}
            </div>
            <p className="label" aria-live="assertive">{open.length ? `${open.length} alert${open.length > 1 ? 's' : ''} to acknowledge` : 'No open alerts'}</p>
            <ul className="m-0 flex flex-col gap-2 p-0">
              {alerts.map((a) => (
                <li key={a.id} className={`list-none rounded-md px-2.5 py-2 text-[12.5px] leading-snug ${a.ack ? 'border border-line text-faint' : a.level === 'RED' ? 'bg-red/15' : 'bg-amber/15'}`}>
                  <b className={`mr-1.5 font-mono text-[10.5px] ${a.ack ? '' : a.level === 'RED' ? 'text-red' : 'text-amber'}`}>{a.level} {clock(a.t)}</b>{a.text}
                  {a.ack ? <span className="ml-1.5 font-mono text-[10.5px]">acknowledged</span> : (
                    <button type="button" onClick={() => setAlerts((old) => old.map((x) => (x.id === a.id ? { ...x, ack: true } : x)))}
                      className="mt-1.5 block rounded border border-line bg-panel px-2 py-1 font-mono text-[11px] text-text">Acknowledge</button>
                  )}
                </li>
              ))}
            </ul>
            <button type="button" onClick={download} disabled={!log.length}
              className="mt-2 rounded-md border border-line bg-panel px-3 py-2 font-mono text-[12.5px] disabled:opacity-40">Download shift log (CSV)</button>
            <p className="text-[11.5px] text-faint">Decision support only. The controller decides.</p>
          </aside>
        </div>
      </div>
    </section>
  );
}
