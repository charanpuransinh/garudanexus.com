#!/bin/bash
# Daily cron: refresh NIFTY-100 stock OHLC + the latest options-expiry
# trading day(s), then auto-commit + auto-push (via auto_commit_push.sh
# + the post-commit hook) — zero manual steps.
cd "$(dirname "$0")/.."
LOG="logs/daily_data_update.log"
mkdir -p logs

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') daily data update starting ====="
  python3 scripts/download_stock_daily.py
  echo "---"
  python3 scripts/download_options_expiry.py
  echo "===== downloads done ====="
} >> "$LOG" 2>&1

bash scripts/auto_commit_push.sh "Automated daily data update: $(date '+%Y-%m-%d')" data/ >> "$LOG" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S') daily data update finished =====" >> "$LOG"
