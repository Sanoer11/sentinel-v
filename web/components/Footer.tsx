import { SITE } from '@/lib/site';

export default function Footer({ generated, git }: { generated?: string; git?: string | null }) {
  return (
    <footer className="mx-auto max-w-page px-4 py-10 text-[12.5px] text-dim sm:px-6">
      <div className="grid gap-8 md:grid-cols-3">
        <div>
          <p className="label">Gnani models used</p>
          <ul className="mt-2 space-y-2 p-0">
            {SITE.models.map((m) => <li key={m.name} className="list-none"><b className="text-text">{m.name}</b> - {m.use}</li>)}
          </ul>
        </div>
        <div>
          <p className="label">Team</p>
          <ul className="mt-2 space-y-2 p-0">
            {SITE.team.map((t) => <li key={t.name} className="list-none"><b className="text-text">{t.name}</b> - {t.role}</li>)}
          </ul>
        </div>
        <div>
          <p className="label">Build</p>
          <p className="mt-2">Data exported {generated ?? '–'}{git ? <> from commit <code className="font-mono text-text">{git}</code></> : null}.</p>
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
