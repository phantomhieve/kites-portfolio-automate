#!/usr/bin/env bash
# kites-automate scheduled runner
# Designed for cron / systemd timers on Linux servers.
#
# Twice weekly: Mon & Thu at 21:00 (Asia/Kolkata). Cron example:
#   CRON_TZ=Asia/Kolkata
#   0 21 * * 1,4 $HOME/kites-automate/scripts/run_scheduled.sh >> $HOME/kites-automate/logs/cron.log 2>&1

set -euo pipefail

# Ensure snap and local bins are in PATH for cron execution
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin:$PATH"

# Snaps (like chromium and chromedriver) fail if XDG_RUNTIME_DIR is not set in cron
if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -d "$XDG_RUNTIME_DIR" ]; then
    export XDG_RUNTIME_DIR="/tmp/runtime-$(id -u)"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
fi

APP_DIR="${KITES_APP_DIR:-$HOME/kites-automate}"
VENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

TEXTFILE_PROM="${KITES_PROM_TEXTFILE:-/var/lib/node-exporter/textfile-collector/kites_automate.prom}"

prom_metrics() {
    KITES_LOG_DIR="$LOG_DIR" "$VENV/bin/python" "$APP_DIR/scripts/export_kites_sync_metrics.py" \
        --log-dir "$LOG_DIR" \
        --textfile "$TEXTFILE_PROM" \
        || printf '%s\n' "WARNING: failed to write Prometheus textfile metrics (${TEXTFILE_PROM})." >>"$LOG_FILE"
}

echo "======================================" | tee -a "$LOG_FILE"
echo "Kites Automate - Scheduled Run"       | tee -a "$LOG_FILE"
echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"

source "$VENV/bin/activate"
cd "$APP_DIR"

TOKEN_EXIT=-99
PORT_EXIT=-99

echo "" | tee -a "$LOG_FILE"
echo "--- Step 1: Token Renewal ---" | tee -a "$LOG_FILE"
set +o pipefail
python3 -m src.kites_automate.cli auto-renew-tokens --force 2>&1 | tee -a "$LOG_FILE"
TOKEN_EXIT=${PIPESTATUS[0]}
set -o pipefail

if [[ "$TOKEN_EXIT" -eq 0 ]]; then
    echo "✅ Token renewal completed" | tee -a "$LOG_FILE"
else
    echo "❌ Token renewal failed — aborting" | tee -a "$LOG_FILE"
fi

FINAL_EXIT=0
echo "" | tee -a "$LOG_FILE"
echo "--- Step 2: Portfolio Update ---" | tee -a "$LOG_FILE"
if [[ "$TOKEN_EXIT" -ne 0 ]]; then
    echo "⚠️ Skipped portfolio update (token step failed)" | tee -a "$LOG_FILE"
    PORT_EXIT=-1
    FINAL_EXIT=1
else
    set +o pipefail
    python3 -m src.kites_automate.cli run-once 2>&1 | tee -a "$LOG_FILE"
    PORT_EXIT=${PIPESTATUS[0]}
    set -o pipefail
    if [[ "$PORT_EXIT" -eq 0 ]]; then
        echo "✅ Portfolio update completed" | tee -a "$LOG_FILE"
    else
        echo "⚠️ Portfolio update finished with errors — check log: $LOG_FILE" | tee -a "$LOG_FILE"
        FINAL_EXIT=1
    fi
fi

SUMMARY_TS=$(date +%s)
{
    printf '\n%s\n' "KITES_RUN_SUMMARY epoch_seconds=${SUMMARY_TS} token_exit=${TOKEN_EXIT} portfolio_exit=${PORT_EXIT}"
    printf '\nFinished: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
} | tee -a "$LOG_FILE"

SUCC=1
if [[ "$FINAL_EXIT" -ne 0 ]]; then SUCC=0; fi
python3 -m src.kites_automate.sync_state \
    --log-dir "$LOG_DIR" \
    --epoch "$SUMMARY_TS" \
    --mode scheduled \
    --success "$SUCC" \
    --token-exit "$TOKEN_EXIT" \
    --portfolio-exit "$PORT_EXIT" \
    --aggregate-exit "$FINAL_EXIT" \
    >>"$LOG_FILE" 2>&1 || printf '%s\n' "WARNING: sync_state (last_pipeline_state.json) write failed" >>"$LOG_FILE"

prom_metrics || true

ls -t "$LOG_DIR"/run_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

exit "$FINAL_EXIT"
