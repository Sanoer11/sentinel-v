// Browser audio for the tower console: play a radio call, and record one from the microphone for Gnani Prisma.

/** Play one clip; resolves when it ends (or fails), so calls are heard one after another like on a real frequency. */
export function play(src: string, keep?: (a: HTMLAudioElement) => void): Promise<void> {
  return new Promise((resolve) => {
    const a = new Audio(src);
    keep?.(a);
    const done = () => resolve();
    a.onended = done; a.onerror = done;
    a.play().catch(done);
  });
}

/** Ask Timbre (through the site's own server, which holds the key) to speak a typed call. Null when unavailable. */
export async function timbre(text: string, channel: string): Promise<{ url: string } | { error: string; status: number }> {
  const r = await fetch('/api/tts/', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, channel }) })
    .catch(() => null);
  if (!r) return { error: 'network', status: 0 };
  if (!r.ok) return { error: (await r.json().catch(() => ({})))?.error ?? `error ${r.status}`, status: r.status };
  return { url: URL.createObjectURL(await r.blob()) };
}

/** Send a recorded WAV to Prisma (through the site's server). */
export async function prisma(wav: Blob, channel: string): Promise<{ text: string; seconds: number } | { error: string; status: number }> {
  const f = new FormData();
  f.set('audio', wav, 'call.wav');
  f.set('channel', channel);
  const r = await fetch('/api/stt/', { method: 'POST', body: f }).catch(() => null);
  if (!r) return { error: 'network', status: 0 };
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return { error: j?.error ?? `error ${r.status}`, status: r.status };
  return { text: j.text ?? '', seconds: j.seconds ?? 0 };
}

/** Microphone recorder. stop() returns the call as 16 kHz mono 16-bit WAV, the format the system sends to Prisma. */
export async function startRecording(maxSeconds = 12, onTimeout?: () => void): Promise<{ stop: () => Promise<Blob> }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const rec = new MediaRecorder(stream);
  const parts: Blob[] = [];
  rec.ondataavailable = (e) => { if (e.data.size) parts.push(e.data); };
  rec.start();
  let stopped: Promise<Blob> | null = null;
  const stop = () => {
    if (stopped) return stopped;
    stopped = new Promise<Blob>((resolve, reject) => {
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        try { resolve(await toWav16k(new Blob(parts, { type: rec.mimeType }))); } catch (e) { reject(e); }
      };
      rec.stop();
    });
    return stopped;
  };
  setTimeout(() => { if (rec.state === 'recording') { if (onTimeout) onTimeout(); else void stop(); } }, maxSeconds * 1000);
  return { stop };
}

async function toWav16k(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  const src = await ctx.decodeAudioData(await blob.arrayBuffer());
  await ctx.close();
  const rate = 16000;
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(src.duration * rate)), rate);
  const node = off.createBufferSource();
  node.buffer = src; node.connect(off.destination); node.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const str = (o: number, s: string) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  str(0, 'RIFF'); out.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true); out.setUint32(24, rate, true);
  out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true); str(36, 'data');
  out.setUint32(40, pcm.length * 2, true);
  pcm.forEach((v, i) => out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([out.buffer], { type: 'audio/wav' });
}
