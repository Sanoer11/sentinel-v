'use client';
import { motion } from 'framer-motion';
import { memo, useEffect, useState } from 'react';

/** On a phone the 760-wide drawing shrinks ~2x, so labels are drawn bigger there to stay readable. */
function useCompact() {
  const [c, setC] = useState(false);
  useEffect(() => {
    const mq = matchMedia('(max-width: 640px)');
    const on = () => setC(mq.matches);
    on(); mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return c;
}
import type { Alert, Occupant } from '@/lib/types';
import { useThemeColors, type ThemeColors } from '@/lib/useThemeColors';

const ACTION_COLOR: Record<string, keyof ThemeColors> = { TAKEOFF: 'red', LAND: 'red', CROSS: 'blue', LINEUP: 'violet', STOPPED: 'faint' };
// several holders on one strip: the most dangerous use decides the colour (a crossing must not paint over a take-off)
const RANK = ['TAKEOFF', 'LAND', 'LINEUP', 'CROSS', 'STOPPED'];
const colourOf = (occ: Occupant[]): keyof ThemeColors => {
  const firm = occ.filter((o) => !o.maybe);
  const use = (firm.length ? firm : occ).map((o) => o.action).sort((x, y) => RANK.indexOf(x) - RANK.indexOf(y))[0];
  return ACTION_COLOR[use] ?? 'blue';
};
/** Where the holder label sits along a strip: Mumbai's 09/27 label moves left of the 14/32 crossing. */
const labelAt = (airport: string, i: number) => (airport === 'VABB' ? (i === 0 ? 0.24 : 0.8) : 0.5);

interface Geom { x1: number; y1: number; x2: number; y2: number }

/** Stylised layouts: parallel runways stacked; Mumbai's 14/32 drawn crossing 09/27 as it does in reality. */
export function stripGeometry(airport: string, strips: string[]): Record<string, Geom> {
  if (airport === 'VABB') {
    return { [strips[0]]: { x1: 70, y1: 120, x2: 690, y2: 120 }, [strips[1]]: { x1: 190, y1: 195, x2: 560, y2: 22 } };
  }
  const out: Record<string, Geom> = {};
  strips.forEach((s, i) => {
    const y = strips.length === 1 ? 105 : 30 + i * (150 / (strips.length - 1));
    out[s] = { x1: 70, y1: y, x2: 690, y2: y };
  });
  return out;
}

function RunwayMap({ airport, strips, picture, alerts }: { airport: string; strips: string[]; picture: Occupant[]; alerts: Alert[] }) {
  const geo = stripGeometry(airport, strips);
  const c = useThemeColors();
  const compact = useCompact();
  const fs = compact ? 22 : 12;
  const reds = alerts.filter((a) => a.level === 'RED');
  const busy = picture.map((o) => `${o.cs} ${o.action} ${o.rw}`).join(', ');
  return (
    <svg viewBox={compact ? '-40 -10 840 230' : '0 0 760 210'} className="h-auto w-full" role="img"
      aria-label={`Runway picture: ${busy || 'all runways free'}${reds.length ? '. RED alert on this call.' : ''}`}>
      {Object.entries(geo).map(([name, g], idx) => {
        const occ = picture.filter((o) => o.strip === name);
        const conflict = occ.length > 0 && reds.some((a) => a.text.includes(name));
        // AMBER "possible conflict" (one runway only heard glued, A14): amber, never red
        const possible = occ.length > 0 && alerts.some((a) => a.kind === 'RUNWAY_CONFLICT_POSSIBLE' && a.text.includes(name));
        const key: keyof ThemeColors = conflict ? 'red' : possible ? 'amber' : occ.length ? colourOf(occ) : 'strip';
        const onlyMaybe = occ.length > 0 && occ.every((o) => o.maybe);
        const fill = c ? c[key] : undefined;
        const ang = (Math.atan2(g.y2 - g.y1, g.x2 - g.x1) * 180) / Math.PI;
        const len = Math.hypot(g.x2 - g.x1, g.y2 - g.y1);
        const [a, b] = name.split('/');
        return (
          <g key={name} transform={`translate(${g.x1},${g.y1}) rotate(${ang})`}>
            <motion.rect x={0} y={-9} width={len} height={18} rx={3} initial={false}
              animate={fill ? { fill, opacity: conflict ? [1, 0.35, 1] : onlyMaybe ? 0.45 : 1 } : { opacity: 1 }}
              transition={conflict ? { opacity: { duration: 0.8, repeat: Infinity }, fill: { duration: 0.3 } } : { duration: 0.35 }}
              className={fill ? '' : 'fill-strip'} stroke={conflict && c ? c.text : 'none'} strokeWidth={2} />
            {Array.from({ length: 9 }, (_, k) => (
              <rect key={k} x={(len * (k + 1)) / 10 - 7} y={-1} width={14} height={2} className="fill-ink" opacity={0.55} />
            ))}
            <text x={-12} y={fs / 3} textAnchor="end" className="fill-dim font-mono" fontSize={fs}>{a}</text>
            <text x={len + 12} y={fs / 3} className="fill-dim font-mono" fontSize={fs}>{b}</text>
            {occ.length > 0 && (
              <motion.text key={occ.map((o) => o.cs + o.action).join()} x={len * labelAt(airport, idx)} y={-15} textAnchor="middle"
                className="fill-text font-mono" fontSize={compact ? 19 : 12} fontWeight={600} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: -15 }}>
                {occ.map((o) => `${o.cs.startsWith('UNIDENTIFIED') ? 'unidentified' : o.cs} ${o.action} ${o.rw}${o.maybe ? ` (maybe: heard ${o.maybe})` : ''}`).join('   ·   ')}
              </motion.text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default memo(RunwayMap);
