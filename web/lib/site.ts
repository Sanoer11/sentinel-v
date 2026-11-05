// Edit these before submitting. Empty strings hide the link.
export const SITE = {
  repoUrl: '',                       // e.g. https://github.com/<you>/sentinel-v
  ciBadge: '',                       // e.g. https://github.com/<you>/sentinel-v/actions/workflows/ci.yml/badge.svg
  team: [
    { name: 'Sanoer', role: 'Speech pipeline, runway engine, experiments, dashboard' },
  ],
  models: [
    { name: 'Gnani Prisma v3.0', use: 'speech-to-text: every radio call (transcribe), a verbatim second listen for glued numbers, a hazard-word hint for vehicle calls' },
    { name: 'Gnani Timbre v3.0', use: 'the spoken alerts (pre-recorded phrase clips) and the dev test voices' },
    { name: 'Gnani Timbre v2.5', use: 'the unseen voices kept back for the one-time locked exam' },
  ],
};
