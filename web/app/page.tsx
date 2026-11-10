'use client';
import { useCallback, useEffect, useState } from 'react';
import Experiments from '@/components/Experiments';
import Footer from '@/components/Footer';
import GnaniModels from '@/components/GnaniModels';
import Hero from '@/components/Hero';
import HowItWorks from '@/components/HowItWorks';
import Limits from '@/components/Limits';
import Nav from '@/components/Nav';
import TowerConsole from '@/components/console/TowerConsole';
import Replay from '@/components/replay/Replay';
import Results from '@/components/results/Results';
import { useSummary } from '@/lib/data';

export default function Page() {
  const summary = useSummary();
  const [scenario, setScenario] = useState<string | null>(null);
  useEffect(() => {
    if (!scenario && summary.data) setScenario(summary.data.scenarios[0]?.id ?? null);
  }, [summary.data, scenario]);

  // used by the hero button and the outcome chart: open a scenario in the replay and scroll to it
  const openReplay = useCallback((id: string) => {
    setScenario(id);
    document.getElementById('replay')?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  return (
    <>
      <a href="#replay" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-panel focus:px-3 focus:py-2">
        Skip to the replay
      </a>
      <Nav />
      <main>
        {summary.isError && (
          <p role="alert" className="mx-auto max-w-page px-6 py-4 text-red">Could not load the results ({String(summary.error)}).</p>
        )}
        <Hero summary={summary.data} onReplay={openReplay} />
        <Replay summary={summary.data} scenario={scenario} setScenario={setScenario} />
        <TowerConsole summary={summary.data} />
        <GnaniModels summary={summary.data} />
        <Results summary={summary.data} onPick={openReplay} />
        <HowItWorks />
        <Experiments />
        <Limits />
      </main>
      <Footer generated={summary.data?.generated} />
    </>
  );
}
