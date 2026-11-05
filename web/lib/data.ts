'use client';
import { useQuery } from '@tanstack/react-query';
import type { Run, Summary } from './types';

// Everything is a static JSON file next to the page (public/data). React Query gives caching (a scenario's runs
// are fetched once, then reused when you click back), loading/error states, and retries on a flaky phone network.

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function useSummary() {
  return useQuery({ queryKey: ['summary'], queryFn: () => getJSON<Summary>('/data/summary.json'), staleTime: Infinity });
}

/** Runs of one scenario, loaded only when that scenario is opened (each file carries every call of every run). */
export function useRuns(scenario: string | null) {
  return useQuery({
    queryKey: ['runs', scenario],
    queryFn: () => getJSON<Run[]>(`/data/runs/${scenario}.json`),
    enabled: !!scenario,
    staleTime: Infinity,
  });
}
