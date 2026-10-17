# Kites Automate — Agent Guidelines & Repository Contract

## Core Mission & Architecture
`kites-automate` provides a secure, fully automated multi-account Zerodha Kite portfolio sync to Google Sheets, running scheduled and unattended on the self-hosted `phantomhive` Linux server.

- **Authentication Automation (`src/kites_automate/auth/`)**: Headless Chromium + TOTP automated login, OAuth redirect interception (`webhook_server.py`), and access token rotation (`token_rotator.py` saving to `~/.kites/`).
- **Portfolio Ingestion & Sync (`src/kites_automate/portfolio/`, `src/kites_automate/kites_adapter.py`)**: Fetches equity holdings and mutual funds across configured Zerodha accounts and synchronizes them to Google Sheets.
- **Sheets IO & Aggregation (`src/kites_automate/sheets/`)**: `SheetManager` writes individual profile tabs with smart formatting cache (`.portfolio_formatting_state.json`), while `SummaryManager` computes consolidated portfolio totals.
- **Scheduled Pipeline & Metrics (`scripts/run_scheduled.sh`, `scripts/export_kites_sync_metrics.py`, `src/kites_automate/sync_state.py`)**: Crontab-triggered execution, log rotation, atomic outcome state tracking (`last_pipeline_state.json`), and Prometheus node_exporter textfile metrics.

---

## Agent Ground Rules

### 1. Super Critical: Never Read or Output Secrets
- **NEVER** view, open, inspect, read, or print `.env`, `.env.*` (except `.env.example`), `credentials.json`, `profiles.json`, or any token/credential files under `~/.kites/`.
- This repository contains secrets to real trading accounts. The production server is self-hosted and isolated at home.
- Never print credentials, tokens, passwords, TOTP secrets, or API keys to stdout, terminal logs, git commit diffs, or markdown artifacts.

### 2. CodeGraph First & Kept Synchronized
- **Explore First**: Call the `codegraph_explore` MCP tool or `/opt/homebrew/bin/codegraph explore <query>` CLI before making edits to inspect source symbols, callers, and dependencies.
- **Keep Synchronized**: Run `codegraph sync` after code changes or file additions.
- Do not commit `.codegraph/codegraph.db` (enforced by `.codegraph/.gitignore`).

### 3. Pre-Commit Hooks
- Pre-commit verification is located in `scripts/pre-commit.sh` and linked to `.git/hooks/pre-commit`.
- The hook verifies:
  1. No secrets (`.env`, `credentials.json`, `profiles.json`, private keys) are staged.
  2. Python bytecode compilation check (`py_compile`).
  3. No merge conflict markers are staged.
  4. CodeGraph index is synced (`codegraph sync`).

### 4. Git Commits & Branching
- Follow conventional commits (`feat: ...`, `fix: ...`, `refactor: ...`, `security: ...`, `docs: ...`).
- Active refactoring and improvements must be developed on the `dev` branch.
- First line under 72 characters, capitalized, imperative mood.

### 5. Production Environment & Resilience
- Server runs headless Ubuntu Linux on cron (`0 21 * * 1,4` in Asia/Kolkata timezone).
- All network operations (Zerodha API, Google Sheets API) must be resilient with retry backoffs and proper error isolation.
- Browser drivers (Chromedriver, Xvfb) must clean up all child and parent processes properly.

### 6. Documentation Accuracy
- Always update `README.md` when features, architectures, CLI flags, or scripts change.
