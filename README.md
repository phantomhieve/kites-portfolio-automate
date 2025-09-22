## Kites Automate

Automation service to:
- Auto-rotate auth token for Kites
- Update portfolio monthly (configurable schedule)
- Email notification after successful update
- Deployable as a systemd service + timer on Ubuntu VM

### New: Proactive token rotation
- Run ad-hoc:
```bash
PYTHONPATH=src python -m kites_automate.cli rotate-tokens
```
- Systemd daily rotation (installed assets):
  - Service: `deploy/systemd/kites-automate-rotate.service`
  - Timer:   `deploy/systemd/kites-automate-rotate.timer` (OnCalendar=daily)
- Enable on VM:
```bash
sudo cp deploy/systemd/kites-automate-rotate.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kites-automate-rotate.timer
sudo systemctl status kites-automate-rotate.timer | cat
```

### Project layout
```
/home/phantomhive/kites-automate-automate
├─ src/kites_automate/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ config.py
│  ├─ logging_setup.py
│  ├─ kites_adapter.py
│  ├─ legacy_adapter.py
│  ├─ auth/token_rotator.py
│  ├─ portfolio/updater.py
│  ├─ notify/emailer.py
│  └─ scheduler/schedule.py
├─ config/defaults.yaml
├─ .env.example
├─ requirements.txt
├─ scripts/install_ubuntu.sh
└─ deploy/systemd/{kites-automate.service,kites-automate.timer,kites-automate-rotate.service,kites-automate-rotate.timer}
```

### Config
- Precedence: **ENV > .env > YAML defaults**
- Keys documented earlier; legacy mode supported.

### Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.kites_automate.cli run-once
# or rotate tokens only
python -m src.kites_automate.cli rotate-tokens
```

### Ubuntu VM setup
- After copying the repo and creating `.env`, enable both timers:
```bash
sudo systemctl enable --now kites-automate.timer
sudo systemctl enable --now kites-automate-rotate.timer
```

### Kites developer console changes
- Create a machine user/API key or client credentials for automation.
- Grant least-privilege scope: portfolio:update.
- If OAuth: enable client-credentials or password flow for headless use; set token TTL and (if used) refresh-token lifetime.
- Allowlist VM egress IP if required.

### Notes
- Local client expected at `/home/phantomhive/kites-automate` or set via env.
- Portfolio watcher module to be added next.


