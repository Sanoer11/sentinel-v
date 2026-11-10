// Gnani Prisma for the tower console: a call spoken into the microphone is transcribed with the same settings the system
// uses on the radio (Prisma v3.0, transcribe format, ATC keyterms and topic; Hindi/English/Marathi for vehicles).
import { allowed, apiKey, BASE, clientIp } from '@/lib/server/gnani';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const KEYTERMS = ['Air India', 'Akasa Air', 'Bird Chaser', 'Bravo', 'Charlie', 'FOD', 'Follow Me', 'IFLY', 'cleared for takeoff',
  'cleared to land', 'cross runway', 'fife', 'hold short', 'holding point', 'line up and wait', 'niner', 'report vacated',
  'runway', 'taxiway', 'tower', 'tree'];
const TOPIC = 'Air traffic control tower radio at an Indian airport: controller clearances, pilot readbacks with callsigns and runway numbers, and airside vehicle radio.';

export async function POST(req: Request) {
  const key = apiKey();
  if (!key) return Response.json({ error: 'live listening not configured' }, { status: 503 });
  let form: FormData;
  try { form = await req.formData(); } catch { return Response.json({ error: 'bad request' }, { status: 400 }); }
  const audio = form.get('audio');
  const channel = String(form.get('channel') ?? 'tower');
  if (!(audio instanceof Blob) || audio.size < 1000 || audio.size > 700_000) {
    return Response.json({ error: 'audio must be a short WAV clip (up to about 15 s)' }, { status: 400 });
  }
  const gate = allowed(clientIp(req), 15);
  if (!gate.ok) return Response.json({ error: gate.why }, { status: 429 });
  const out = new FormData();
  out.set('model', 'prisma-v3.0');
  out.set('format', 'transcribe');
  out.set('language_code', channel === 'airside' ? 'hi-IN,en-IN,mr-IN' : 'en-IN');
  out.set('keyterms', JSON.stringify(KEYTERMS));
  out.set('topic', TOPIC);
  out.set('audio_file', audio, 'call.wav');
  const t0 = Date.now();
  const r = await fetch(`${BASE}/stt/v3`, { method: 'POST', headers: { 'X-API-Key-ID': key }, body: out }).catch(() => null);
  if (!r) return Response.json({ error: 'Prisma unreachable' }, { status: 502 });
  const j = await r.json().catch(() => null);
  if (!r.ok || !j?.success) return Response.json({ error: `Prisma ${r.status}` }, { status: 502 });
  return Response.json({ text: String(j.transcript ?? '').trim(), seconds: (Date.now() - t0) / 1000 });
}
