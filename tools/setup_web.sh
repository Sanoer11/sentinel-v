#!/bin/sh
# Run once from the repo root after unzipping: sh tools/setup_web.sh
# 1) lets git track the site's synthetic audio (root .gitignore ignores *.wav), 2) reinstalls the safety hook.
for line in 'web/node_modules/' 'web/.next/' 'web/out/' '!web/public/audio/' '!web/public/audio/*.wav'; do
  grep -qxF "$line" .gitignore || echo "$line" >> .gitignore
done
sh tools/install_hooks.sh
echo "Done. Next: python export_web.py"
