import { histogram, pct, ratio, runLabel, verdictTone } from '@/lib/format';

describe('format helpers', () => {
  it('colours verdicts, never green for a miss or a false alarm', () => {
    expect(verdictTone('ON TIME')).toBe('green');
    expect(verdictTone('LATE')).toBe('amber');
    expect(verdictTone('MISSED')).toBe('red');
    expect(verdictTone('FALSE RED')).toBe('red');
  });

  it('labels runs the way the results talk about them', () => {
    expect(runLabel('clean', 0)).toBe('clean audio');
    expect(runLabel('10', 7)).toBe('10 dB · noise 7');
  });

  it('does not divide by zero', () => {
    expect(ratio(0, 0)).toBe('–');
    expect(pct(3, 0)).toBe('–');
    expect(pct(137, 160)).toBe('86%');
  });

  it('bins latencies and puts the slow tail into the last bin', () => {
    const h = histogram([0.05, 0.42, 0.44, 17.5], 0.1, 2.5);
    expect(h[0].count).toBe(1);
    expect(h[4].count).toBe(2);
    expect(h[h.length - 1]).toMatchObject({ label: '≥2.5', count: 1 });
    expect(h.reduce((a, b) => a + b.count, 0)).toBe(4);
  });
});
