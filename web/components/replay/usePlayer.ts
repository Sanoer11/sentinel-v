'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Run } from '@/lib/types';

/**
 * Plays a run the way the tower would live it: each call's radio audio, THEN the engine's verdict (it only
 * decides once the call has ended), THEN the spoken RED alert, then a short gap (real gaps compressed).
 * Missing audio (or a blocked autoplay) never stalls the replay: it falls back to a timer.
 */
export function usePlayer(run: Run | undefined) {
  const [shown, setShown] = useState(-1);
  const [revealed, setRevealed] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const playingRef = useRef(false);
  const shownRef = useRef(-1);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    if (audio.current) { audio.current.pause(); audio.current = null; }
  };
  // pausing mid-call still shows that call's verdict (the engine already decided it)
  const stop = useCallback(() => {
    playingRef.current = false; setPlaying(false); clear();
    setRevealed((r) => Math.max(r, shownRef.current));
  }, []);
  const reset = useCallback(() => { stop(); shownRef.current = -1; setShown(-1); setRevealed(-1); setSpeaking(null); }, [stop]);
  useEffect(() => reset, [run, reset]);

  const playFile = (src: string | null | undefined, done: () => void) => {
    if (!src) { timer.current = setTimeout(done, 1600); return; }
    const a = new Audio(src);
    audio.current = a;
    a.onended = done;
    a.onerror = () => { timer.current = setTimeout(done, 1000); };
    a.play().catch(() => { timer.current = setTimeout(done, 1400); });
  };

  const playFrom = useCallback((i: number) => {
    if (!run || i >= run.steps.length) { stop(); return; }
    const s = run.steps[i];
    shownRef.current = i; setShown(i); setSpeaking(null);
    playFile(s.audio, () => {
      setRevealed(i);
      const next = () => {
        if (!playingRef.current) return;
        const n = run.steps[i + 1];
        const gap = n ? Math.min(2.2, Math.max(0.8, (n.t - s.t) / 8)) : 0;
        timer.current = setTimeout(() => playingRef.current && playFrom(i + 1), gap * 1000);
      };
      if (s.spoken) { setSpeaking(s.spoken.says); playFile(s.spoken.file, next); } else next();
    });
  }, [run, stop]);

  const play = useCallback(() => {
    if (!run) return;
    clear();
    playingRef.current = true; setPlaying(true);
    playFrom(shown >= run.steps.length - 1 ? 0 : shown + 1);
  }, [run, shown, playFrom]);

  const step = useCallback(() => {
    if (!run || shown >= run.steps.length - 1) return;
    stop();
    const i = shown + 1;
    shownRef.current = i; setShown(i); setRevealed(i);
    setSpeaking(run.steps[i].spoken?.says ?? null);
  }, [run, shown, stop]);

  useEffect(() => () => clear(), []);
  return { shown, revealed, playing, speaking, play, stop, step, reset };
}
