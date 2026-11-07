import { SITE } from '@/lib/site';

export default function Footer({ generated }: { generated?: string }) {
  return (
    <footer className="mx-auto max-w-page px-4 py-10 text-[12.5px] text-dim sm:px-6">
      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <p className="label">Gnani models used</p>
          <ul className="mt-2 space-y-2 p-0">
            {SITE.models.map((m) => <li key={m.name} className="list-none"><b className="text-text">{m.name}</b> - {m.use}</li>)}
          </ul>
        </div>
        <div>
          <p className="label">Build</p>
          <p className="mt-2">Results data exported {generated ?? '–'}.</p>
          {SITE.repoUrl && <p className="mt-2"><a className="text-signal underline-offset-2 hover:underline" href={SITE.repoUrl}>Source on GitHub</a></p>}
          {SITE.ciBadge && (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="mt-3" src={SITE.ciBadge} alt="CI status" height={20} />
          )}
          <p className="mt-3">#GnaniAI #GreatIndianAIInternshipChallenge</p>
        </div>
      </div>
    </footer>
  );
}
