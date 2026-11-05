'use client';
import { useEffect, useState } from 'react';

const NAMES = ['ink', 'panel', 'line', 'text', 'dim', 'faint', 'signal', 'red', 'amber', 'green', 'blue', 'violet', 'strip'] as const;
export type ThemeColors = Record<(typeof NAMES)[number], string>;

function read(): ThemeColors {
  const css = getComputedStyle(document.documentElement);
  return Object.fromEntries(NAMES.map((n) => [n, `rgb(${css.getPropertyValue(`--${n}`).trim().split(/\s+/).join(',')})`])) as ThemeColors;
}

/** Real colour strings for chart libraries (they cannot use CSS variables), re-read when the theme flips. */
export function useThemeColors(): ThemeColors | null {
  const [c, setC] = useState<ThemeColors | null>(null);
  useEffect(() => {
    setC(read());
    const mo = new MutationObserver(() => setC(read()));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, []);
  return c;
}
