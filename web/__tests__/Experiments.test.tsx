import { fireEvent, render, screen, within } from '@testing-library/react';
import Experiments from '@/components/Experiments';
import { EXPERIMENTS } from '@/lib/experiments';

describe('Experiments table', () => {
  it('lists every experiment, failed ones included', () => {
    render(<Experiments />);
    const rows = screen.getAllByRole('button', { expanded: false });
    expect(rows).toHaveLength(EXPERIMENTS.length);
    expect(screen.getAllByText('FAIL').length).toBeGreaterThan(5);
  });

  it('search narrows the list', () => {
    render(<Experiments />);
    fireEvent.change(screen.getByLabelText('Search experiments'), { target: { value: 'squelch' } });
    const ids = screen.getAllByRole('button', { expanded: false }).map((b) => b.textContent?.replace('▸', ''));
    expect(ids).toEqual(['A4']);
  });

  it('a row expands to show the rule that was fixed before the result', () => {
    render(<Experiments />);
    const a6 = screen.getAllByRole('button', { expanded: false }).find((b) => b.textContent?.includes('A6'))!;
    fireEvent.click(a6);
    const detail = document.getElementById('exp-A6')!;
    expect(within(detail).getByText(/1 of 15 fixed/)).toBeInTheDocument();
    expect(within(detail).getAllByText('rule, fixed first')).toHaveLength(1);
  });

  it('every part has a rule and a result (no empty claims)', () => {
    for (const e of EXPERIMENTS) for (const p of e.parts) {
      expect(p.rule.length).toBeGreaterThan(0);
      expect(p.result.length).toBeGreaterThan(10);
    }
  });
});
