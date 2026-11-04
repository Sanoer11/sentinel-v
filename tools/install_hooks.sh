#!/bin/sh
# Run once:  sh tools/install_hooks.sh
cp tools/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit && echo "Safety hook installed: .git/hooks/pre-commit"
