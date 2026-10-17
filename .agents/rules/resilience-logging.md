# Resilience & Logging Policy

## Policy:
1. **Defensive Error Handling & Retries**:
   - Trading API calls (Zerodha Kite Connect) and Google Sheets API calls can encounter transient network issues, rate limits (HTTP 429), or temporary outages.
   - All network I/O and external API calls must be protected with retries using exponential backoff with jitter.
   - When processing multiple profiles/accounts, failure of a single account must not crash the entire pipeline. Isolate account failures, log diagnostic error reasons, continue remaining accounts, and report aggregated status at the end.

2. **Clean, Structured, and Safe Logging**:
   - Use standard `logging` with clear severity levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
   - Redact all secrets and credentials in logs. Never log API secret strings, access tokens, TOTP codes, or full passwords. Log only string lengths or safe masked identifiers if necessary.
   - Record run summaries with machine-readable metadata (e.g. `last_pipeline_state.json`) for alerting and observability.

3. **Subprocess & Resource Lifecycle Cleanup**:
   - Headless browser drivers (Chromium/Chromedriver) and virtual framebuffers (`Xvfb`) must be cleanly terminated in `finally` blocks.
   - Prevent zombie processes, dangling browser sessions, and leaked memory on the long-running host server.
