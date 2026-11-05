'use client';
import { Bar, BarChart, Brush, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { histogram } from '@/lib/format';
import { useThemeColors } from '@/lib/useThemeColors';

/** How long Prisma took per radio call (0.1 s bins). Drag the brush under the chart to zoom into the tail. */
export default function LatencyChart({ values }: { values: number[] }) {
  const c = useThemeColors();
  if (!c) return <div className="h-[300px]" />;
  const data = histogram(values, 0.1, 2.5);
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ left: 0, right: 12, top: 8, bottom: 0 }} accessibilityLayer>
        <CartesianGrid vertical={false} stroke={c.line} />
        <XAxis dataKey="label" tick={{ fill: c.dim, fontSize: 10.5 }} stroke={c.line} interval={4} />
        <YAxis allowDecimals={false} tick={{ fill: c.dim, fontSize: 11 }} stroke={c.line} width={36} />
        <Tooltip cursor={{ fill: c.line, opacity: 0.4 }}
          contentStyle={{ background: c.panel, border: `1px solid ${c.line}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: c.text }} itemStyle={{ color: c.text }}
          labelFormatter={(l) => `${l} s to ${(parseFloat(String(l)) + 0.1).toFixed(1)} s`} formatter={(v) => [v, 'calls']} />
        <Bar dataKey="count" fill={c.signal} radius={[3, 3, 0, 0]} animationDuration={700} />
        <Brush dataKey="label" height={22} stroke={c.signal} fill={c.panel} travellerWidth={8} />
      </BarChart>
    </ResponsiveContainer>
  );
}
