#!/usr/bin/env bash
# ==============================================================================
# Kites Automate — Phantomhive Server Migration Script
# ==============================================================================
# Safely upgrades the deployed installation on phantomhive server to the new
# unified src/kites_automate architecture, removing legacy kites_core while
# strictly preserving production secrets (.env, profiles.json, credentials.json).
# ==============================================================================

set -eo pipefail

SERVER_HOST=${SERVER_HOST:-"phantomhive"}
SERVER_USER=${SERVER_USER:-"phantomhive"}
TARGET_DIR=${TARGET_DIR:-"/home/${SERVER_USER}/kites-automate"}
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

echo "============================================================"
echo " 🪁 Kites Automate — Migration to Phantomhive Server"
echo " Target Host: ${SSH_TARGET}:${TARGET_DIR}"
echo "============================================================"

# Step 1: Pre-flight SSH check
echo "==> [1/5] Verifying SSH connectivity to ${SSH_TARGET}..."
ssh -o BatchMode=yes -o ConnectTimeout=5 "${SSH_TARGET}" "uptime" >/dev/null || {
    echo "❌ ERROR: Cannot reach ${SSH_TARGET}. Check SSH configuration and keys."
    exit 1
}
echo "✅ SSH connection verified."

# Step 2: Backup and protect server secrets before migration
echo "==> [2/5] Creating backup of server secrets on remote host..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  TARGET_DIR="$HOME/kites-automate"
  BACKUP_DIR="$HOME/.kites_migration_backup_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP_DIR"

  if [ -d "$TARGET_DIR" ]; then
    echo "Backing up production configuration to $BACKUP_DIR..."
    [ -f "$TARGET_DIR/.env" ] && cp "$TARGET_DIR/.env" "$BACKUP_DIR/.env"
    [ -f "$TARGET_DIR/profiles.json" ] && cp "$TARGET_DIR/profiles.json" "$BACKUP_DIR/profiles.json"
    
    # If credentials.json is inside kites_core, promote it to root
    if [ -f "$TARGET_DIR/kites_core/credentials.json" ] && [ ! -f "$TARGET_DIR/credentials.json" ]; then
      echo "Promoting kites_core/credentials.json to root credentials.json..."
      cp "$TARGET_DIR/kites_core/credentials.json" "$TARGET_DIR/credentials.json"
    fi
    [ -f "$TARGET_DIR/credentials.json" ] && cp "$TARGET_DIR/credentials.json" "$BACKUP_DIR/credentials.json"
    
    # Remove stale legacy directories
    echo "Cleaning up legacy directories..."
    rm -rf "$TARGET_DIR/kites_core" "$TARGET_DIR/Users"
  fi
  echo "✅ Remote secrets backed up and legacy folders pruned."
EOF

# Step 3: Rsync clean codebase (excluding secrets, virtualenv, and runtime files)
echo "==> [3/5] Deploying clean unified codebase..."
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

# Step 4: Install/verify dependencies in virtual environment
echo "==> [4/5] Updating server Python virtual environment..."
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
  echo "✅ Virtual environment ready."
EOF

# Step 5: Post-migration diagnostic status check
echo "==> [5/5] Executing post-migration diagnostics on server..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  cd "$HOME/kites-automate"
  source .venv/bin/activate
  python3 -m src.kites_automate.cli status
EOF

echo ""
echo "============================================================"
echo " 🎉 Migration to phantomhive server completed successfully!"
echo "============================================================"
