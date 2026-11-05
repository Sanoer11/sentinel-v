'use client';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Summary } from '@/lib/types';
import { useThemeColors } from '@/lib/useThemeColors';

/**
 * The readback check on every tower call + pilot readback pair in the dev test sets (clean, 20, 10, 5, 0 dB).
 * A wrong readback shown as MATCH would be a silent miss: that is the number that must stay 0.
 */
export default function ReadbackChart({ readback }: { readback: Summary['readback'] }) {
  const c = useThemeColors();
  if (!c) return <div className="h-[220px]" />;
  const row = (name: string, r: Record<string, number>) => ({
    name, RED: r.MISMATCH ?? 0, AMBER: r.INCOMPLETE ?? 0, MATCH: r.MATCH ?? 0, UNPAIRED: (r.NO_CLEARANCE ?? 0) + (r.UNMATCHED ?? 0),
  });
  const data = [row('pilot really read back wrong', readback.wrong), row('pilot read back correctly', readback.correct)];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={18} accessibilityLayer>
        <CartesianGrid horizontal={false} stroke={c.line} />
        <XAxis type="number" tick={{ fill: c.dim, fontSize: 11 }} stroke={c.line} />
        <YAxis type="category" dataKey="name" width={150} tick={{ fill: c.text, fontSize: 11.5 }} stroke={c.line} />
        <Tooltip cursor={{ fill: c.line, opacity: 0.4 }} contentStyle={{ background: c.panel, border: `1px solid ${c.line}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: c.text }} itemStyle={{ color: c.text }} />
        <Legend wrapperStyle={{ fontSize: 11.5 }} />
        <Bar dataKey="RED" name="RED mismatch" stackId="a" fill={c.red} />
        <Bar dataKey="AMBER" name="AMBER: asked to confirm" stackId="a" fill={c.amber} />
        <Bar dataKey="MATCH" name="shown as match" stackId="a" fill={c.green} />
        <Bar dataKey="UNPAIRED" name="could not be paired" stackId="a" fill={c.faint} />
      </BarChart>
    </ResponsiveContainer>
  );
}
