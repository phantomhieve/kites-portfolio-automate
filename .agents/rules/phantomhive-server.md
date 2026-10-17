# Phantomhive Server Environment & Deployment Guidelines

## Policy:
1. **Host Environment & Isolation**:
   - The production instance runs on a dedicated, isolated self-hosted server at home (`phantomhive` / `/home/phantomhive/kites-automate`).
   - Host OS: Ubuntu Linux (64-bit).
   - Execution Model: Non-interactive automated execution via `crontab`:
     `CRON_TZ=Asia/Kolkata`
     `0 21 * * 1,4 /home/phantomhive/kites-automate/scripts/run_scheduled.sh >> /home/phantomhive/kites-automate/logs/cron.log 2>&1`
   - Python Virtual Environment: `/home/phantomhive/kites-automate/.venv` with Python 3.13 / 3.14.

2. **Headless Browser Constraints**:
   - Snap-based Chromium or apt-based Chromium is installed on the server.
   - Chromium binary paths and Chromedriver binary locations may differ from desktop macOS. The automated auth module must dynamically discover binary locations (e.g. `/snap/bin/chromium.chromedriver`, `/snap/chromium/current/...`, `/usr/bin/chromedriver`).
   - `Xvfb` is required for virtual display (`:99`) when running headless OAuth flows.

3. **Deployment & State Preservation**:
   - Production `.env`, `credentials.json`, `profiles.json`, and tokens under `~/.kites/` reside strictly on the server and must never be overwritten, modified, or checked into version control.
   - Run verification and synchronization tests in dry-run mode or isolated test suites before deploying code changes.
