#!/bin/bash
# One-time setup (per clone): point git at this repo's version-controlled
# hooks so every `git commit` auto-pushes afterward. core.hooksPath itself
# is local git config, not something git versions — this script is what
# makes it reproducible on a fresh clone.
set -e
cd "$(dirname "$0")/.."
chmod +x scripts/hooks/*
git config core.hooksPath scripts/hooks
echo "Git hooks configured: core.hooksPath -> scripts/hooks (auto-push after every commit)"
