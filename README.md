# Kites Automate

[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Kites Automate** is a production-grade, unattended multi-account portfolio tracker for Zerodha Kite. It automatically renews Zerodha session access tokens via headless Chromium with TOTP authentication, fetches live equity and mutual fund holdings, and synchronizes them to Google Sheets with consolidated cross-portfolio summaries.

Designed and optimized to run scheduled and headless on the self-hosted **`phantomhive`** Linux server at home.

---

## Key Features

- **Automated Hands-Free Token Renewal**: Performs headless Chromium authentication, automatic TOTP code injection, and OAuth callback interception (`webhook_server.py`) to renew Kite access tokens without manual browser clicks.
- **Multi-Account Aggregation**: Syncs equity holdings and mutual funds across multiple configured Zerodha accounts into dedicated Google Sheets tabs, plus a unified executive **Summary** worksheet.
- **Quota-Aware Smart Formatting**: Caches sheet styling state locally (`.portfolio_formatting_state.json`, `.summary_formatting_state.json`) to minimize Google Sheets API calls and prevent HTTP 429 quota exhaustion.
- **Exponential Backoff Resilience**: External network calls (Google Sheets API and Zerodha Kite Connect) feature exponential backoff retry decorators with jitter for transient error recovery.
- **Strict Secret Protection & Redaction**: Built-in `SecretRedactingFilter` scrubs passwords, API secrets, and Bearer tokens from stdout and cron log streams. Real trading credentials never leak to logs or git.
- **Scheduled Cron Execution**: Runs unattended bi-weekly on Mondays and Thursdays at 21:00 IST via `scripts/run_scheduled.sh`.
- **Prometheus & Grafana Observability**: Emits atomic pipeline state (`last_pipeline_state.json`) and node_exporter textfile metrics (`scripts/export_kites_sync_metrics.py`).

---

## Architecture Overview

```
kites-automate/
├── src/kites_automate/
│   ├── cli.py                     # Unified CLI (run, auto-renew-tokens, status, test-sheets)
│   ├── config.py                  # Pydantic settings & environment configuration
│   ├── profiles.py                # Multi-account profiles.json loader & resolver
│   ├── logging_setup.py           # Structured logging with SecretRedactingFilter
│   ├── sync_state.py              # Atomic run outcome state recorder (last_pipeline_state.json)
│   ├── kites_adapter.py           # UnifiedKitesAdapter linking KiteConnect to Sheets
│   ├── auth/
│   │   ├── fully_automated_auth.py# Headless Chromium + TOTP + OAuth flow
│   │   ├── token_rotator.py       # ~/.kites/ access token rotation and caching
│   │   ├── webhook_server.py      # Local OAuth redirect callback receiver
│   │   └── kite_auth.py           # Token-based and interactive Kite session manager
│   ├── sheets/
│   │   ├── client.py              # Resilient Google Sheets SheetManager with retries
│   │   ├── portfolio.py           # Holdings, mutual funds, and P&L calculations
│   │   └── summary.py             # Consolidated cross-account portfolio overview
│   ├── portfolio/
│   │   └── updater.py             # Multi-account sync orchestrator
│   ├── notify/
│   │   └── emailer.py             # Summary and error email alerts
│   └── utils/
│       ├── helpers.py             # Safe float parsing and currency formatting
│       └── retry.py               # Exponential backoff retry decorator
├── kites_core/                    # Backward-compatibility shims
├── config/defaults.yaml           # Account defaults and configuration
├── scripts/
│   ├── run_scheduled.sh           # Main cron pipeline script
│   ├── deploy_linux.sh            # Safe rsync deployment to phantomhive server
│   ├── export_kites_sync_metrics.py# Prometheus node_exporter metrics exporter
│   └── pre-commit.sh              # Pre-commit hook (secret prevention & syntax verification)
├── tests/                         # Unit test suite
├── AGENTS.md                      # Agent rules, security contracts, and guidelines
└── profiles.json.example          # Account profiles schema template
```

---

## Security & Secrets Policy

> [!IMPORTANT]
> **Super Critical**: This service manages real trading accounts. The production server is self-hosted and isolated. **Never inspect or print `.env`, `credentials.json`, `profiles.json`, or files under `~/.kites/`**.

1. **`~/.kites/credentials.json`**: Contains Zerodha account user IDs, passwords, and TOTP base32 secrets. Stored outside the repository with strict `chmod 600` permissions.
2. **`credentials.json`**: Google Cloud Service Account private key with Editor permissions on the destination spreadsheet. Ignored by `.gitignore`.
3. **`.env`**: Stores per-profile API keys and secrets (`<account>_api_key`, `<account>_api_secret`), SMTP credentials, and timezone settings. Ignored by `.gitignore`.
4. **`profiles.json`**: Maps account profile names to environment variable keys and exclusion lists. Ignored by `.gitignore`.

---

## Quick Start & Local Setup

### 1. Prerequisites
- Python 3.13 or 3.14
- Chromium and Chromedriver installed (or via Snap on Ubuntu)
- Xvfb (for headless display on Linux)

### 2. Environment Setup
```bash
# Clone and enter directory
cd kites-automate

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration Files
```bash
# Create environment file from template
cp .env.example .env
# Edit .env with your Zerodha API keys and email configuration

# Create profiles configuration
cp kites_core/profiles.json.example profiles.json
# Edit profiles.json with your profile definitions

# Create Zerodha credentials file for automated login
mkdir -p ~/.kites
chmod 700 ~/.kites
cp docs/credentials_template.json ~/.kites/credentials.json
chmod 600 ~/.kites/credentials.json

# Place Google Cloud Service Account key
cp /path/to/service_account.json ./credentials.json
```

---

## CLI Usage

The service exposes a unified CLI via `python -m src.kites_automate.cli`:

```bash
# Display system diagnostics, token validity, and recent run outcome
python -m src.kites_automate.cli status

# Verify Google Sheets connectivity
python -m src.kites_automate.cli test-sheets

# Perform automated headless Chromium login + TOTP token renewal
python -m src.kites_automate.cli auto-renew-tokens

# Run portfolio synchronization for all configured accounts
python -m src.kites_automate.cli run

# Run portfolio synchronization for a single account
python -m src.kites_automate.cli run --account HUF

# Send a test email alert
python -m src.kites_automate.cli send-test-email

# Run with verbose debug logging
python -m src.kites_automate.cli --debug run
```

---

## Production Deployment on Phantomhive Server

The production server runs headless Ubuntu Linux on cron.

### Scheduled Crontab
On the `phantomhive` server, crontab triggers execution bi-weekly on Mondays and Thursdays at 21:00 IST:

```cron
CRON_TZ=Asia/Kolkata
0 21 * * 1,4 /home/phantomhive/kites-automate/scripts/run_scheduled.sh >> /home/phantomhive/kites-automate/logs/cron.log 2>&1
```

### Deploying Updates to the Server
Deploy safely from macOS or developer machine:

```bash
# Deploy code without touching production secrets or runtime cache
bash scripts/deploy_linux.sh
```

---

## Testing

Run the automated test suite with `pytest`:

```bash
pytest tests/ -v
```

All tests run locally in sandbox mode without requiring live broker credentials or Google Sheets API quotas.

---

## Developer Guidelines & Pre-Commit Hook

Before committing code, verify checks pass:

```bash
# Run pre-commit checks (secret scanning, syntax check, CodeGraph sync)
bash scripts/pre-commit.sh
```

All contributions follow conventional commits (`feat: ...`, `fix: ...`, `refactor: ...`, `security: ...`) on the `dev` branch.
