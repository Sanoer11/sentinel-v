// Server-only helpers for the tower console's live Gnani calls. The API key is read from the server's environment
// (Vercel: Project Settings -> Environment Variables -> GNANI_API_KEY; local: web/.env.local). It is never sent to the browser.
export const BASE = process.env.GNANI_BASE || 'https://api.vachana.ai';   // GNANI_BASE only for local tests

export function apiKey(): string | null {
  return process.env.GNANI_API_KEY || null;
}

// Simple guards so a public page cannot run up the bill: per-visitor rate limit + a daily cap per server instance.
const hits = new Map<string, { n: number; reset: number }>();
let day = { date: '', n: 0 };
export function allowed(ip: string, perTenMin: number): { ok: boolean; why?: string } {
  const now = Date.now();
  const today = new Date().toISOString().slice(0, 10);
  if (day.date !== today) day = { date: today, n: 0 };
  const cap = Number(process.env.GNANI_DAILY_CAP ?? 400);
  if (day.n >= cap) return { ok: false, why: 'daily limit reached' };
  const h = hits.get(ip);
  if (!h || h.reset < now) hits.set(ip, { n: 1, reset: now + 10 * 60_000 });
  else if (h.n >= perTenMin) return { ok: false, why: 'too many calls, wait a few minutes' };
  else h.n++;
  day.n++;
  return { ok: true };
}

export function clientIp(req: Request): string {
  return (req.headers.get('x-forwarded-for') ?? '').split(',')[0].trim() || 'local';
}

const DIGIT = ['zero', 'one', 'two', 'tree', 'four', 'fife', 'six', 'seven', 'eight', 'niner'];
/** Radio style, as the scenarios are spoken: "29R" -> "two niner right", "725" -> "seven two fife". */
export function icao(text: string): string {
  return text
    .replace(/\b(\d{1,2})\s*([LRC])\b/gi, (_, d: string, s: string) => `${d} ${{ L: 'left', R: 'right', C: 'centre' }[s.toUpperCase() as 'L']}`)
    .replace(/\d+/g, (d) => ` ${d.split('').map((c) => DIGIT[+c]).join(' ')} `)
    .replace(/\s+/g, ' ')
    .replace(/ ([,.?!])/g, '$1')
    .trim();
}

/** Timbre sends a streaming WAV header (sizes 0xFFFFFFFF). Write the real sizes so every browser can play it. */
export function fixWav(buf: Buffer): Buffer {
  if (buf.length > 44 && buf.toString('ascii', 0, 4) === 'RIFF') {
    buf.writeUInt32LE(buf.length - 8, 4);
    const at = buf.indexOf('data', 12, 'ascii');
    if (at > 0) buf.writeUInt32LE(buf.length - at - 8, at + 4);
  }
  return buf;
}
