# Kites Automate

Fully automated Zerodha portfolio tracker. Logs into Kite Connect via headless Chromium, rotates access tokens, fetches holdings, and updates Google Sheets — completely hands-free on a bi-weekly cron schedule.

---

## What it does

- **Auto-renews Zerodha access tokens** via headless browser login + TOTP (no manual intervention)
- **Fetches live portfolio** (equity + MF holdings) for multiple accounts
- **Updates Google Sheets** — one tab per account, plus a consolidated Summary tab
- **Runs on a cron schedule** — bi-weekly (Mon + Thu) at 1:30 AM

---

## Project layout

```
kites-automate/
├── src/kites_automate/
│   ├── cli.py                   # Entry point: run-once, auto-renew-tokens
│   ├── kites_adapter.py         # Fetches portfolio via Kite API + writes to Sheets
│   ├── config.py                # Settings (ENV > .env > config/defaults.yaml)
│   ├── auth/
│   │   ├── fully_automated_auth.py  # Headless Chromium login + TOTP + OAuth
│   │   ├── token_rotator.py     # Token read/write/refresh from ~/.kites/
│   │   └── webhook_server.py    # Local HTTP server to capture OAuth redirect
│   ├── portfolio/updater.py     # Orchestrates multi-account update + Summary sheet
│   └── notify/emailer.py        # Optional failure email notifications
├── kites_core/
│   ├── main.py                  # PortfolioManager: data processing + sheet writes
│   └── kites/                   # Sheet/auth library (SheetManager, SummaryManager)
├── config/defaults.yaml         # Default settings
├── scripts/
│   ├── run_scheduled.sh         # Cron runner script (token renewal + portfolio update)
│   ├── deploy_linux.sh          # One-shot deploy script for Linux server
│   └── install_ubuntu.sh        # Dependency installer for Ubuntu
├── docs/credentials_template.json  # ~/.kites/credentials.json template
├── profiles.json                # Account profiles (gitignored — contains real names)
├── .env                         # Secrets (gitignored)
└── .env.example                 # Secrets template
```

---

## Setup

### 1. Dependencies
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Credentials
```bash
# Copy and fill in API keys, SMTP, etc.
cp .env.example .env

# Create Zerodha login credentials for automated browser login
# See docs/credentials_template.json for format
mkdir -p ~/.kites
cp docs/credentials_template.json ~/.kites/credentials.json
# Edit ~/.kites/credentials.json with real Zerodha usernames, passwords, TOTP secrets
```

### 3. Profiles
Create `profiles.json` at the project root (see `kites_core/profiles.json.example`):
```json
{
  "profiles": [
    { "profile_name": "Account1", "api_key_env": "account1_api_key", "api_secret_env": "account1_api_secret" }
  ],
  "settings": { "spreadsheet_name": "Portfolio", "summary_sheet_name": "Summary" }
}
```

### 4. Google Sheets credentials
Place your Google service account `credentials.json` inside `kites_core/`.

---

## Usage

```bash
# Renew all Zerodha access tokens (headless browser login)
python -m src.kites_automate.cli auto-renew-tokens

# Update all portfolio sheets (fetches holdings → writes to Google Sheets)
python -m src.kites_automate.cli run-once

# Run both (same as cron)
bash scripts/run_scheduled.sh
```

---

## Cron setup (Linux server)

```bash
# View current cron
crontab -l

# Install bi-weekly cron (Mon + Thu at 1:30 AM)
(crontab -l 2>/dev/null; echo "30 1 * * 1,4 /home/mobileci/kites-automate/scripts/run_scheduled.sh >> /home/mobileci/kites-automate/logs/cron.log 2>&1") | crontab -

# View logs
tail -f ~/kites-automate/logs/cron.log
```

---

## Configuration

Precedence: **ENV vars > `.env` file > `config/defaults.yaml`**

Key `.env` variables:
```dotenv
account1_api_key=...
account1_api_secret=...
account2_api_key=...
account2_api_secret=...
account3_api_key=...
account3_api_secret=...

# Optional email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
NOTIFY_EMAIL=...
```

---

## Token storage

Tokens are stored as flat JSON files in `~/.kites/`:
```
~/.kites/
├── Account1_access_token.txt
├── Account2_access_token.txt
├── Account3_access_token.txt
└── credentials.json      # Zerodha login credentials for browser automation
```
