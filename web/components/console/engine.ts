// Loads the real Python parser and runway engine into the browser (Pyodide = CPython compiled to WebAssembly).
// The alert voice is the recorded Gnani Timbre phrase clips in public/audio/voice/ (the system joins the same clips).
// The files in public/engine/ are byte-for-byte copies of the ones at the repo root; CI fails if they drift.
// Loaded only when someone presses "Start the console", so the rest of the site never pays for it.

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
const FILES = ['sentinel_parse.py', 'sentinel_actions.py', 'sentinel_state.py', 'sentinel_voice.py', 'console_bridge.py'];

export interface EngineAlert { level: 'RED' | 'AMBER' | 'INFO'; kind: string; text: string }
export interface Hold { strip: string; cs: string; action: string; rw: string; left: number; maybe?: string }
export interface CallResult {
  status: string; read: string | null; instructions: { runway: string | null; action: string | null }[];
  notes: string[]; alerts: EngineAlert[]; spoken: string[] | null; picture: Hold[];
}
export interface TickResult { alerts: EngineAlert[]; spoken: string[] | null; picture: Hold[] }
export interface Engine {
  start(airport: string, traffic: string[]): void;
  setTraffic(traffic: string[]): void;
  call(t: number, channel: string, text: string): CallResult;
  tick(t: number): TickResult;
}

interface Bridge { start(a: string, t: string): string; set_traffic(t: string): string; call(t: number, c: string, x: string): string; tick(t: number): string }
interface Pyodide { FS: { writeFile(path: string, data: string): void }; runPython(code: string): unknown; pyimport(name: string): Bridge }
declare global { interface Window { loadPyodide?: (o: { indexURL: string }) => Promise<Pyodide> } }

function script(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('could not load the Python runtime'));
    document.head.appendChild(s);
  });
}

let pending: Promise<Engine> | null = null;

export function loadEngine(): Promise<Engine> {
  if (!pending) {
    pending = (async () => {
      if (!window.loadPyodide) await script(`${PYODIDE}pyodide.js`);
      const py = await window.loadPyodide!({ indexURL: PYODIDE });
      for (const f of FILES) {
        const res = await fetch(`/engine/${f}`);
        if (!res.ok) throw new Error(`engine file ${f}: HTTP ${res.status}`);
        py.FS.writeFile(`/home/pyodide/${f}`, await res.text());
      }
      py.runPython("import sys\nif '/home/pyodide' not in sys.path: sys.path.insert(0, '/home/pyodide')");
      const b = py.pyimport('console_bridge');
      return {
        start: (airport, traffic) => { b.start(airport, JSON.stringify(traffic)); },
        setTraffic: (traffic) => { b.set_traffic(JSON.stringify(traffic)); },
        call: (t, channel, text) => JSON.parse(b.call(t, channel, text)) as CallResult,
        tick: (t) => JSON.parse(b.tick(t)) as TickResult,
      } satisfies Engine;
    })().catch((e) => { pending = null; throw e; });
  }
  return pending;
}

const WORDS: Record<string, string> = {
  IFLY: 'IGO', 'AIR INDIA': 'AIC', VISTARA: 'VTI', 'AKASA AIR': 'AKJ', 'FOLLOW ME': 'FOLLOWME', 'BIRD CHASER': 'BIRDCHASER',
};

/** "IFLY 512" / "Air India 101" / "IGO512" / "Bird Chaser 2" -> the code the engine uses, or null. */
export function toCallsign(input: string): string | null {
  const s = input.trim().toUpperCase().replace(/\s+/g, ' ');
  const code = s.match(/^(IGO|AIC|VTI|AKJ|FOLLOWME|BIRDCHASER) ?(\d{1,4})$/);
  if (code) return code[1] + code[2];
  const word = s.match(/^(IFLY|AIR INDIA|VISTARA|AKASA AIR|FOLLOW ME|BIRD CHASER) ?(\d{1,4})$/);
  return word ? WORDS[word[1]] + word[2] : null;
}
