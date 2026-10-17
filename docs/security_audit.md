# Security Audit & Hardening Report

**Repository**: `kites-automate`  
**Date**: October 2026  
**Target Environment**: `phantomhive` self-hosted server  
**Status**: PASSED / HARDENED

---

## 1. Executive Summary

A comprehensive security audit of `kites-automate` was conducted to protect real trading accounts and sensitive credentials on the isolated, self-hosted `phantomhive` Linux server. All identified attack surfaces, process table exposure vectors, legacy code paths, and potential information leaks have been remediated.

---

## 2. Key Findings & Remediations

### Finding 1: Command-Line Argument Secret Leakage (CRITICAL — REMEDIATED)
- **Vulnerability**: In `fully_automated_auth.py`, `KiteConnect.generate_session` was formerly invoked by spawning a separate Python subprocess:
  ```python
  # VULNERABLE PATTERN (PREVIOUSLY)
  subprocess.run([current_python, "-c", f'...api_key="{self.api_key}"...api_secret="{self.api_secret}"...'])
  ```
  On a multi-process Linux machine, command-line arguments are visible to any process running under the same user via `ps aux` or `/proc/<pid>/cmdline`.
- **Remediation**: Completely replaced the subprocess invocation with direct, in-process Python execution:
  ```python
  # SECURED IN-PROCESS EXECUTION
  from kiteconnect import KiteConnect
  kite = KiteConnect(api_key=self.api_key)
  data = kite.generate_session(request_token, api_secret=self.api_secret)
  return data.get("access_token")
  ```
  Secrets never touch the OS process table or shell arguments.

---

### Finding 2: Personal Identifiers & Account Names in Tracked Files (MEDIUM — REMEDIATED)
- **Vulnerability**: Tracked templates (`docs/credentials_template.json`, `profiles.json.example`, `config/defaults.yaml`, `fully_automated_auth.py` docstrings) contained real account names.
- **Remediation**: All tracked repository files were scrubbed and standardized on generic placeholders (`Account1`, `Account2`, `Account3`). Real account names are confined strictly to untracked, local configuration files (`profiles.json`, `.env`).

---

### Finding 3: Logging Stream Credential Scrubbing (HIGH — REMEDIATED)
- **Vulnerability**: External API errors or debug logging could potentially print raw response tokens or Authorization headers.
- **Remediation**: Implemented `SecretRedactingFilter` in `src/kites_automate/logging_setup.py`. It inspects all log messages and arguments using regular expressions to automatically sanitize `password=`, `api_key=`, `api_secret=`, `totp_secret=`, `access_token=`, and `Bearer ...` strings to `[REDACTED]`.

---

### Finding 4: Legacy Code Duplication & Ambiguous Paths (LOW — REMEDIATED)
- **Vulnerability**: The coexistence of `kites_core` and `src/kites_automate` led to overlapping credentials search paths and legacy adapter fallbacks.
- **Remediation**: Deleted `kites_core/`, `legacy_adapter.py`, and `kites_context.md`. The codebase is 100% unified under `src/kites_automate/`.

---

### Finding 5: Git Secret Prevention Guardrails (HIGH — ENFORCED)
- **Remediation**: Installed and hardened `scripts/pre-commit.sh` as a Git pre-commit hook:
  1. Blocks commits containing `.env`, `credentials.json`, `profiles.json`, private keys, or certificates.
  2. Runs Python bytecode compilation (`py_compile`) on all staged files.
  3. Rejects merge conflict markers.
  4. Automatically synchronizes the CodeGraph knowledge graph index.

---

### Finding 6: Configuration Proliferation & Service Account Key Collision (HIGH — REMEDIATED)
- **Vulnerability**: 
  1. Configs were fragmented across 5 sources (`config/defaults.yaml`, `kites_core/credentials.json`, `~/.kites/credentials.json`, `profiles.json`, `.env`).
  2. `credentials.json` collision: `~/.kites/credentials.json` was used for Zerodha login passwords, but `client.py` also searched `~/.kites/credentials.json` for Google Cloud Service Account keys, risking fatal parse crashes.
  3. The production server `.env` had accumulated 14 obsolete legacy variables (`KITES_BASE_URL`, `LEGACY_*`, `KITES_LOCAL_*`).
- **Remediation**:
  1. Disambiguated Google Service Account search to `GOOGLE_APPLICATION_CREDENTIALS` and `~/.kites/google_service_account.json`. Removed ambiguous `~/.kites/credentials.json` from Google credentials lookup.
  2. Unified all trading account credentials (login, TOTP, API key, API secret) directly in `~/.kites/credentials.json` (chmod 600, outside repo).
  3. Completely deleted `config/defaults.yaml`.
  4. Consolidated `.env` to minimal runtime operational flags only.

---

## 3. Phantomhive Server Security Posture Audit

| Audit Item | Current State on Server | Risk Evaluation | Action Taken |
|---|---|---|---|
| `~/.kites/` Directory | `drwx------` (0700) | Secure (phantomhive user only) | Preserved |
| `~/.kites/credentials.json` | `-rw-------` (0600) | Secure (phantomhive user only) | Upgraded to hold API keys & secrets |
| Google Service Account Key | Was inside `kites_core/credentials.json` (0600) | Moderate (buried in legacy repo directory) | Promoted to `~/.kites/google_service_account.json` & `./credentials.json` |
| Server `.env` | `-rw-------` (0600), 31 variables | Cluttered (14 dead legacy variables) | Pruned dead keys, streamlined to runtime configs |
| Cron Job (`0 21 * * 1,4`) | Runs `scripts/run_scheduled.sh` headless | Low | Verified wrapper script and log rotation |
| Subprocess Execution | Previous code passed secrets to `python -c` in CLI | Critical (visible in `ps aux`) | Eliminated via in-process KiteConnect execution |

---

## 4. Security Checklist for Server Deployment

| Check | Requirement | Status |
|---|---|---|
| Zero Secrets in Git | No private keys, passwords, or tokens in tracked files | ✅ VERIFIED |
| File Permissions | `chmod 700 ~/.kites` and `chmod 600 ~/.kites/credentials.json` | ✅ ENFORCED |
| Environment Permissions | `chmod 600 /home/phantomhive/kites-automate/.env` | ✅ ENFORCED |
| Process Sandboxing | No API keys passed in CLI process arguments | ✅ VERIFIED |
| Network Retries | Exponential backoff with jitter on Sheets and Kite APIs | ✅ IMPLEMENTED |
| Browser Teardown | `Xvfb :99` and `chromedriver` cleaned up in `finally` blocks | ✅ IMPLEMENTED |
| Config Minimalism | 2-artifact architecture (`~/.kites/credentials.json` + clean `.env`) | ✅ HARDENED |
