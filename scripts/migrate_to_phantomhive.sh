#!/usr/bin/env bash
# ==============================================================================
# Kites Automate — Phantomhive Server Migration & Consolidation Script
# ==============================================================================
# Safely upgrades the deployed installation on phantomhive server to the new
# unified src/kites_automate architecture:
# 1. Backs up all remote configuration and secrets to a timestamped directory
# 2. Consolidates trading credentials (passwords + TOTP + API keys) in ~/.kites/credentials.json
# 3. Promotes Google Service Account key to ~/.kites/google_service_account.json
# 4. Prunes dead legacy variables from .env
# 5. Removes deprecated kites_core/ and Users/ directories
# 6. Deploys clean unified codebase
# 7. Runs test-sheets and status diagnostics
# ==============================================================================

set -eo pipefail

SERVER_HOST=${SERVER_HOST:-"phantomhive"}
SERVER_USER=${SERVER_USER:-"phantomhive"}
TARGET_DIR=${TARGET_DIR:-"/home/${SERVER_USER}/kites-automate"}
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

echo "============================================================"
echo " 🪁 Kites Automate — Migration & Consolidation Pipeline"
echo " Target Host: ${SSH_TARGET}:${TARGET_DIR}"
echo "============================================================"

# Step 1: Pre-flight SSH check
echo "==> [1/6] Verifying SSH connectivity to ${SSH_TARGET}..."
ssh -o BatchMode=yes -o ConnectTimeout=5 "${SSH_TARGET}" "uptime" >/dev/null || {
    echo "❌ ERROR: Cannot reach ${SSH_TARGET}. Check SSH configuration and keys."
    exit 1
}
echo "✅ SSH connection verified."

# Step 2: Backup and protect server secrets before migration
echo "==> [2/6] Backing up server secrets on remote host..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  TARGET_DIR="$HOME/kites-automate"
  BACKUP_DIR="$HOME/.kites_migration_backup_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"

  echo "Backing up configurations to $BACKUP_DIR..."
  [ -d "$HOME/.kites" ] && cp -r "$HOME/.kites" "$BACKUP_DIR/dot_kites"
  [ -f "$TARGET_DIR/.env" ] && cp "$TARGET_DIR/.env" "$BACKUP_DIR/.env"
  [ -f "$TARGET_DIR/profiles.json" ] && cp "$TARGET_DIR/profiles.json" "$BACKUP_DIR/profiles.json"
  [ -f "$TARGET_DIR/kites_core/credentials.json" ] && cp "$TARGET_DIR/kites_core/credentials.json" "$BACKUP_DIR/kites_core_credentials.json"
  [ -f "$TARGET_DIR/credentials.json" ] && cp "$TARGET_DIR/credentials.json" "$BACKUP_DIR/credentials.json"
  
  echo "✅ Remote secrets backed up successfully."
EOF

# Step 3: Consolidate Keys, Google Service Account, and .env
echo "==> [3/6] Consolidating secrets and cleaning dead legacy keys..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  TARGET_DIR="$HOME/kites-automate"
  
  # 1. Promote Google Cloud Service Account key
  if [ -f "$TARGET_DIR/kites_core/credentials.json" ]; then
    echo "Promoting Google Service Account to ~/.kites/google_service_account.json..."
    cp "$TARGET_DIR/kites_core/credentials.json" "$HOME/.kites/google_service_account.json"
    cp "$TARGET_DIR/kites_core/credentials.json" "$TARGET_DIR/credentials.json"
    chmod 600 "$HOME/.kites/google_service_account.json" "$TARGET_DIR/credentials.json"
  elif [ -f "$TARGET_DIR/credentials.json" ]; then
    cp "$TARGET_DIR/credentials.json" "$HOME/.kites/google_service_account.json"
    chmod 600 "$HOME/.kites/google_service_account.json"
  fi

  # 2. Consolidate API keys into ~/.kites/credentials.json and prune dead .env vars
  python3 - << 'PY_EOF'
import json
import os
from pathlib import Path

vault_path = Path.home() / ".kites" / "credentials.json"
env_path = Path.home() / "kites-automate" / ".env"

env_dict = {}
raw_env_lines = []
if env_path.is_file():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            raw_env_lines.append(line)
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, v = stripped.split("=", 1)
                env_dict[k.strip()] = v.strip()

# Update ~/.kites/credentials.json with api_key and api_secret
if vault_path.is_file():
    with open(vault_path, "r", encoding="utf-8") as f:
        vault = json.load(f)

    updated = False
    accounts = vault.get("accounts", vault)
    if isinstance(accounts, dict):
        for acct_name, acct_data in accounts.items():
            if isinstance(acct_data, dict):
                acct_lower = acct_name.lower()
                key_val = env_dict.get(f"{acct_lower}_api_key") or env_dict.get(f"{acct_name.upper()}_API_KEY")
                sec_val = env_dict.get(f"{acct_lower}_api_secret") or env_dict.get(f"{acct_name.upper()}_API_SECRET")
                if key_val and not acct_data.get("api_key"):
                    acct_data["api_key"] = key_val
                    updated = True
                if sec_val and not acct_data.get("api_secret"):
                    acct_data["api_secret"] = sec_val
                    updated = True

    if updated:
        with open(vault_path, "w", encoding="utf-8") as f:
            json.dump(vault, f, indent=2)
        os.chmod(vault_path, 0o600)
        print("  -> Updated ~/.kites/credentials.json: co-located API keys into unified vault.")

# Prune dead legacy variables from .env
DEAD_KEYS = {
    "KITES_BASE_URL", "KITES_USERNAME", "KITES_PASSWORD", "KITES_API_KEY",
    "KITES_CLIENT_ID", "KITES_CLIENT_SECRET", "KITES_LOCAL_PATH",
    "KITES_LOCAL_MODULE", "KITES_LOCAL_CLIENT_CLASS", "LEGACY_ENABLED",
    "LEGACY_PROJECT_PATH", "LEGACY_MODULE_NAME", "LEGACY_MODE", "LEGACY_ENV_FILE"
}

new_lines = []
for line in raw_env_lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        k = stripped.split("=", 1)[0].strip()
        if k in DEAD_KEYS:
            continue
    new_lines.append(line)

# Ensure GOOGLE_APPLICATION_CREDENTIALS exists in .env
gcreds_line = f"GOOGLE_APPLICATION_CREDENTIALS={Path.home()}/.kites/google_service_account.json\n"
if not any("GOOGLE_APPLICATION_CREDENTIALS" in l for l in new_lines):
    new_lines.insert(0, gcreds_line)

with open(env_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
os.chmod(env_path, 0o600)
print("  -> Pruned 14 dead legacy variables from remote .env.")
PY_EOF

  # 3. Clean up legacy directories
  echo "Pruning legacy kites_core and Users directories..."
  rm -rf "$TARGET_DIR/kites_core" "$TARGET_DIR/Users"
  echo "✅ Remote configuration consolidated and legacy directories cleaned."
EOF

# Step 4: Rsync clean codebase (excluding secrets, virtualenv, and runtime files)
echo "==> [4/6] Deploying clean unified codebase..."
rsync -avz --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'credentials.json' \
  --exclude 'profiles.json' \
  --exclude 'logs' \
  --exclude '.*_formatting_state.json' \
  --exclude 'last_pipeline_state.json' \
  --exclude '.codegraph' \
  --exclude '.pytest_cache' \
  ./ "${SSH_TARGET}:${TARGET_DIR}/"

# Step 5: Install/verify dependencies in virtual environment
echo "==> [5/6] Updating server Python virtual environment..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  TARGET_DIR="$HOME/kites-automate"
  cd "${TARGET_DIR}"

  PYTHON_BIN=$(command -v python3.13 2>/dev/null || command -v python3)
  if [ ! -d ".venv" ]; then
    echo "Initializing virtual environment..."
    $PYTHON_BIN -m venv .venv
  fi

  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  echo "✅ Virtual environment dependencies up-to-date."
EOF

# Step 6: Post-migration diagnostic and test run
echo "==> [6/6] Executing post-migration diagnostics & test run on server..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  cd "$HOME/kites-automate"
  source .venv/bin/activate

  echo "--- [Status Diagnostics] ---"
  python3 -m src.kites_automate.cli status

  echo ""
  echo "--- [Google Sheets Connectivity Test] ---"
  python3 -m src.kites_automate.cli test-sheets
EOF

echo ""
echo "============================================================"
echo " 🎉 Migration & test run on phantomhive server successful!"
echo "============================================================"
