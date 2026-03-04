#!/usr/bin/env bash
# kites-automate scheduled runner
# Designed to be run via cron on the Linux server
# Bi-weekly: Mon and Thu at 1:30 AM IST
#
# Cron entry (add via: crontab -e):
#   30 1 * * 1,4 /home/mobileci/kites-automate/scripts/run_scheduled.sh >> /home/mobileci/kites-automate/logs/cron.log 2>&1

set -euo pipefail

APP_DIR="/home/mobileci/kites-automate"
VENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

echo "======================================" | tee -a "$LOG_FILE"
echo "Kites Automate - Scheduled Run"       | tee -a "$LOG_FILE"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

# Activate virtual environment
source "$VENV/bin/activate"

cd "$APP_DIR"

# Step 1: Renew all Zerodha access tokens via automated browser login
echo "" | tee -a "$LOG_FILE"
echo "--- Step 1: Token Renewal ---" | tee -a "$LOG_FILE"
if python3 -m src.kites_automate.cli auto-renew-tokens 2>&1 | tee -a "$LOG_FILE"; then
    echo "✅ Token renewal completed" | tee -a "$LOG_FILE"
else
    echo "❌ Token renewal failed — aborting" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 2: Update all portfolio sheets
echo "" | tee -a "$LOG_FILE"
echo "--- Step 2: Portfolio Update ---" | tee -a "$LOG_FILE"
if python3 -m src.kites_automate.cli run-once 2>&1 | tee -a "$LOG_FILE"; then
    echo "✅ Portfolio update completed" | tee -a "$LOG_FILE"
else
    echo "⚠️ Portfolio update finished with errors — check log: $LOG_FILE" | tee -a "$LOG_FILE"
fi

# Clean up old logs (keep last 30)
ls -t "$LOG_DIR"/run_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

echo "" | tee -a "$LOG_FILE"
echo "Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')" | tee -a "$LOG_FILE"
