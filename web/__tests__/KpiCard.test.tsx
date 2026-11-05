import { render, screen } from '@testing-library/react';
import KpiCard from '@/components/KpiCard';

// framer-motion's useInView needs IntersectionObserver, which jsdom does not have
beforeAll(() => {
  class IO { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } root = null; rootMargin = ''; thresholds = []; }
  (global as unknown as { IntersectionObserver: unknown }).IntersectionObserver = IO;
});

describe('KpiCard', () => {
  it('names the measurement in its accessible label, with the exact value and suffix', () => {
    render(<KpiCard label="false RED, normal traffic" value={2} suffix=" / 20" detail="runs of a normal Delhi sequence that raised any RED" />);
    expect(screen.getByRole('figure', { name: 'false RED, normal traffic: 2 / 20' })).toBeInTheDocument();
  });

  it('always shows what the number means', () => {
    render(<KpiCard label="median hearing time" value={0.49} decimals={2} suffix=" s" detail="Prisma per call over 900 calls" />);
    expect(screen.getByText('Prisma per call over 900 calls')).toBeInTheDocument();
    expect(screen.getByText('median hearing time')).toBeInTheDocument();
  });
});
