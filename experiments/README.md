# Experiments A1-A17

Each file is one experiment. Its pass/fail rule is written in the docstring **before** the result, and the
result (PASS or FAIL, with the numbers) is recorded under it. A fix stays behind a flag, off, until its rule
passes. Failed fixes stay off and are kept here. A5 (context fill, FAIL) has no file of its own; all 17 are
on the site under Experiments.

Run one from the repo root, e.g. `python experiments/exp_a17.py`. Most replay saved transcripts from
`results/` (no API key, no cost); some need the API key or local audio that is not in the repo.

Re-running an older experiment today compares against the current engine, where its fix may already be on,
so it can print no change or FAIL. The result recorded in each file is the one from the day it was run.
