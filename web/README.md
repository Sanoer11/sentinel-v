# Sentinel-V · web

The public site for Sentinel-V: replay of every measured scenario run (with the radio audio and the spoken
alert), the measured results, every experiment with its rule, and the limits.

**Live:** `<your Vercel URL>` - judges need nothing installed.

| | |
|---|---|
| Stack | Next.js 14 (static export) · TypeScript · Tailwind · Framer Motion · Recharts · TanStack Query |
| Data | `public/data/*.json` + `public/audio/*.mp3`, written by `python export_web.py` from the saved runs |
| Server | none. The site never calls Gnani Prisma or Timbre and holds no API key |
| Audio | synthetic only: Gnani Timbre voices through a simulated VHF radio |

## Sections
- **Replay** - pick a scenario and a run (clean or 10 dB with noise recording 0-19). Play gives each call's radio audio,
  then the engine's verdict, then the spoken RED alert. Big text = what Prisma heard; small text = what was said.
  The runway drawing shows who holds each runway after every call and flashes on a conflict.
- **Results** - on-time / late / missed per scenario (click a bar to replay it), Prisma time per call (drag to zoom),
  and the readback check (wrong readbacks missed must stay 0).
- **Experiments** - A1-A13: each fix, the rule written before its result, the result, PASS / FAIL. Searchable.
- **How it works**, **Limits**.

## Update the data
```
python export_web.py            # from the repo root, on the machine with the results + API key
cd web && npm run build         # optional local check
git add web/public && git commit -m "Site data" && git push
```
Vercel rebuilds on the push.

## Develop
```
cd web
npm ci
npm run dev                     # http://localhost:3000
npm run lint && npm run typecheck && npm test && npm run build
```

## CI/CD
- `.github/workflows/ci.yml` runs on every push and pull request: the 141 Python engine tests, then lint,
  type-check, Jest tests and a production build of this site.
- Vercel's GitHub integration deploys: every push to `main` goes live, every pull request gets a preview link
  in a comment. No deploy token is stored in the repository.

**One-time Vercel setup:** vercel.com → Add New → Project → import the GitHub repo → set **Root Directory** to
`web` → Deploy. That's all; the framework (Next.js) is detected.

## Design notes
- Dark by default (a tower cab at night), with a light mode. Only two alert colours, red and amber, and they
  always come with the word (RED / AMBER), never colour alone.
- Animation carries meaning: the runway lights up with the engine's picture, the verdict appears only when the
  call has ended (that is when the engine decides), counters run once. All motion respects "reduce motion".
- Performance: charts are lazy-loaded; each scenario's runs load only when opened and are cached; the page is
  static HTML on a CDN.
