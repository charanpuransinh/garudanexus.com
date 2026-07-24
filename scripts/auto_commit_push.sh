#!/bin/bash
# auto_commit_push.sh ["commit message"] [path...]
#
# Stages the given paths (repo root if none given), commits with the
# given message (or an auto-generated one), and lets the post-commit
# hook push it. Meant to be called at the end of any automated task
# (a cron job, a script) so "task complete" always implies "committed
# and on its way to GitHub" — no separate manual git push step, ever.
set -e
cd "$(dirname "$0")/.."

MSG="${1:-Automated update: $(date '+%Y-%m-%d %H:%M')}"
if [ "$#" -gt 0 ]; then shift; fi
if [ "$#" -eq 0 ]; then
  PATHS=(".")
else
  PATHS=("$@")
fi

git add -- "${PATHS[@]}"

if git diff --cached --quiet; then
  echo "auto_commit_push: nothing staged, nothing to commit."
  exit 0
fi

git commit -m "$MSG"
echo "auto_commit_push: committed. Push is running via the post-commit hook (see .git/auto_push.log)."
