'use client';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Summary, Verdict } from '@/lib/types';
import { useThemeColors } from '@/lib/useThemeColors';

const ORDER: { key: Verdict; label: string; tone: 'green' | 'amber' | 'violet' | 'red' }[] = [
  { key: 'ON TIME', label: 'on time', tone: 'green' },
  { key: 'LATE', label: 'late (at the readback)', tone: 'amber' },
  { key: 'OTHER-RED', label: 'a different RED', tone: 'violet' },
  { key: 'MISSED', label: 'missed', tone: 'red' },
  { key: 'FALSE RED', label: 'false RED', tone: 'red' },
];

/** Every 10 dB run of every scenario, stacked by outcome. Click a scenario to open it in the replay. */
export default function OutcomeChart({ summary, onPick }: { summary: Summary; onPick: (id: string) => void }) {
  const c = useThemeColors();
  if (!c) return <div className="h-[340px]" />;
  const data = summary.scenarios.map((s) => ({ id: s.id, ...Object.fromEntries(ORDER.map((o) => [o.key, s.counts.noisy[o.key] ?? 0])) }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }} barCategoryGap={7}
        onClick={(e) => e?.activeLabel && onPick(String(e.activeLabel))} style={{ cursor: 'pointer' }}
        accessibilityLayer>
        <CartesianGrid horizontal={false} stroke={c.line} />
        <XAxis type="number" allowDecimals={false} tick={{ fill: c.dim, fontSize: 11 }} stroke={c.line} />
        <YAxis type="category" dataKey="id" width={118} tick={{ fill: c.text, fontSize: 11.5, fontFamily: 'IBM Plex Mono' }} stroke={c.line} />
        <Tooltip cursor={{ fill: c.line, opacity: 0.4 }}
          contentStyle={{ background: c.panel, border: `1px solid ${c.line}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: c.text, fontFamily: 'IBM Plex Mono' }} itemStyle={{ color: c.text }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: c.dim }} />
        {ORDER.map((o) => (
          <Bar key={o.key} dataKey={o.key} name={o.label} stackId="a" fill={c[o.tone]}
            fillOpacity={o.key === 'FALSE RED' ? 0.55 : 0.9} isAnimationActive animationDuration={700} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
