## Kites Automate - Execution Context

Purpose: Enable kites-automate to run this project non-interactively and understand inputs/outputs.

### What this project does
- Fetches holdings from Zerodha Kite per profile and updates a Google Sheets spreadsheet.
- Modes: Smart (format when needed), Minimal (data only), Force Format, Show Status, Reset State.

### Key files
- `main.py`: Entry; exposes functions `smart_update`, `minimal_update`, `force_format`, `show_status`, `reset_formatting_state`.
- `profiles.json`: Profiles and settings. Keys `api_key_env`, `api_secret_env`, `token_file`, `profile_name`.
- `kites/auth/kite_auth.py`: Zerodha auth and token handling (tokens stored under `~/.kites/`).
- `kites/sheets/portfolio.py`: Portfolio processing. Uses `opening_quantity` for stock quantities.
- `kites/sheets/sheet_manager.py`, `kites/sheets/summary.py`: Google Sheets IO/formatting.
- State files: `.portfolio_formatting_state.json`, `.summary_formatting_state.json` (local, used for formatting state).

### Inputs required
1) Environment variables (from `.env` or set by runner) per `profiles.json`:
   - For each profile: `<api_key_env>`, `<api_secret_env>`
   - Example based on current `profiles.json`:
     - `account1_api_key`, `account1_api_secret`
     - `account2_api_key`, `account2_api_secret`
     - `account3_api_key`, `account3_api_secret`

2) Google Sheets credentials file:
   - `credentials.json` at project root (Service Account JSON)

3) Profiles/config:
   - `profiles.json` with:
     - `settings.spreadsheet_name` (e.g., "Portfolio")
     - `settings.summary_sheet_name` (e.g., "Summary")

### Outputs
- Updates/creates worksheets inside the spreadsheet named in `profiles.json`:
  - One worksheet per profile (`profile_name`)
  - One `Summary` worksheet

### Non-interactive commands (preferred for automation)
Run from repo root with a Python venv activated and env vars loaded.

- Smart Update (recommended formatting behavior):
  ```bash
  python -c "from dotenv import load_dotenv; load_dotenv(); from main import smart_update; smart_update()"
  ```

- Minimal Update (data only, lowest quota):
  ```bash
  python -c "from dotenv import load_dotenv; load_dotenv(); from main import minimal_update; minimal_update()"
  ```

- Force Format (high quota usage):
  ```bash
  python -c "from dotenv import load_dotenv; load_dotenv(); import builtins; builtins.input=lambda *_: 'y'; from main import force_format; force_format()"
  ```

- Show Status (read-only):
  ```bash
  python -c "from dotenv import load_dotenv; load_dotenv(); from main import show_status; show_status()"
  ```

- Reset Formatting State (deletes local state files):
  ```bash
  python -c "from dotenv import load_dotenv; load_dotenv(); import builtins; builtins.input=lambda *_: 'y'; from main import reset_formatting_state; reset_formatting_state()"
  ```

Notes:
- These commands bypass the interactive menu by importing and invoking functions directly.
- For commands that prompt via `input()`, input is stubbed to `"y"` where needed.

### Runtime assumptions
- Python venv is active (dependencies from `requirements.txt` installed).
- `credentials.json` present at project root and has access to the target spreadsheet.
- Env vars are set in the environment or `.env` exists in repo root.

### Data flow summary
Zerodha Kite → `KiteAuthManager` (token under `~/.kites/…`) → `PortfolioManager` (`opening_quantity` used for stocks) → `SheetManager` → Google Sheets (profile tabs + `Summary`).

### Failure modes kites-automate should surface
- Missing env vars for any profile (warning per profile; profile skipped).
- Missing/invalid `credentials.json` (Sheets access failure).
- Kite token invalid/expired (login flow triggers; headless runs will fail unless a valid token exists in `~/.kites/<token_file>`).
- Google API quota or Zerodha rate limits (retry or switch to Minimal mode).


