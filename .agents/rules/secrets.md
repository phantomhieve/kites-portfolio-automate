# Secret & Credentials Security Policy

## Policy:
1. **Never Read or Output Secrets**:
   - **CRITICAL**: This repository automates Zerodha trading accounts with live credentials, passwords, TOTP secrets, Kite API keys, and Google Sheets Service Account credentials.
   - **NEVER** view, open, inspect, read, or print `.env`, `.env.*` (except `.env.example`), `credentials.json`, `profiles.json`, or any files under `~/.kites/credentials.json`.
   - Never output credentials, tokens, passwords, TOTP secrets, or API keys to stdout, terminal logs, git commit diffs, or markdown artifacts.

2. **Defense in Depth**:
   - Always ensure that `.gitignore` strictly ignores `.env`, `.env.*`, `credentials.json`, `profiles.json`, `*.key.json`, and local state files.
   - Never log full API keys or auth tokens. If logging is required for debugging, log only the string length or a sanitized label (e.g., `key_len=32`, never `key=xyz...`).
   - Clean up temporary files, screenshots, and browser session artifacts immediately. Never leave session cookies or tokens in `/tmp`.
