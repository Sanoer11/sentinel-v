// Gnani Timbre for the tower console: a typed radio call is spoken in the voice of whoever is "talking".
import { allowed, apiKey, BASE, clientIp, fixWav, icao } from '@/lib/server/gnani';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// The same Timbre voices the scenarios use: tower Avinash, pilot Riyaa, vehicles Poorvi (Hinglish) / Zahira (Marathi).
const VOICES: Record<string, [string, string, string]> = {
  tower: ['Avinash', 'timbre-v3.0', 'en-IN'],
  pilot: ['Riyaa', 'timbre-v3.0', 'en-IN'],
  airside: ['Poorvi', 'timbre-v2.5', 'hi-en'],
  airside_mr: ['Zahira', 'timbre-v2.5', 'mr-IN'],
};
const cache = new Map<string, Buffer>();

export async function POST(req: Request) {
  const key = apiKey();
  if (!key) return Response.json({ error: 'live voice not configured' }, { status: 503 });
  let body: { text?: unknown; channel?: unknown };
  try { body = await req.json(); } catch { return Response.json({ error: 'bad request' }, { status: 400 }); }
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  const channel = typeof body.channel === 'string' ? body.channel : 'tower';
  if (!text || text.length > 160) return Response.json({ error: 'text must be 1-160 characters' }, { status: 400 });
  const who = channel === 'airside' ? (/[ऀ-ॿ]/.test(text) ? 'airside_mr' : 'airside') : channel === 'pilot' ? 'pilot' : 'tower';
  const [voice, model, language] = VOICES[who];
  const spoken = icao(text);
  const id = `${who}|${spoken}`;
  const hit = cache.get(id);
  if (hit) return new Response(new Uint8Array(hit), { headers: { 'content-type': 'audio/wav', 'x-voice': voice } });
  const gate = allowed(clientIp(req), 20);
  if (!gate.ok) return Response.json({ error: gate.why }, { status: 429 });
  const r = await fetch(`${BASE}/api/v1/tts/inference`, {
    method: 'POST',
    headers: { 'X-API-Key-ID': key, 'content-type': 'application/json' },
    body: JSON.stringify({ text: spoken, voice, model, language, speed: 1.0,
      audio_config: { sample_rate: 16000, num_channels: 1, sample_width: 2, encoding: 'linear_pcm', container: 'wav' } }),
  }).catch(() => null);
  if (!r || !r.ok) return Response.json({ error: `Timbre ${r ? r.status : 'unreachable'}` }, { status: 502 });
  const wav = fixWav(Buffer.from(await r.arrayBuffer()));
  if (cache.size > 200) cache.delete(cache.keys().next().value as string);
  cache.set(id, wav);
  return new Response(new Uint8Array(wav), { headers: { 'content-type': 'audio/wav', 'x-voice': voice } });
}
