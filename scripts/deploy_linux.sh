#!/usr/bin/env bash
set -eo pipefail

# Production target host (can be overridden via environment variables)
SERVER_USER=${SERVER_USER:-"phantomhive"}
SERVER_HOST=${SERVER_HOST:-"phantomhive"}
TARGET_DIR=${TARGET_DIR:-"/home/${SERVER_USER}/kites-automate"}
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

echo "==> Deploying kites-automate to ${SSH_TARGET}:${TARGET_DIR}..."

# 1. Sync repository files safely without overwriting server secrets, state, or venv
echo "==> Syncing files to remote host..."
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
  ./ "${SSH_TARGET}:${TARGET_DIR}/"

# 2. Configure dependencies on remote host
echo "==> Verifying Python environment on server..."
ssh "${SSH_TARGET}" bash -s << 'EOF'
  set -eo pipefail
  
  TARGET_DIR="$HOME/kites-automate"
  cd "${TARGET_DIR}"
  
  PYTHON_BIN=$(command -v python3.13 2>/dev/null || command -v python3)
  echo "Server Python: $($PYTHON_BIN -V)"
  
  if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_BIN -m venv .venv
  fi
  
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  
  echo "✅ Remote deployment completed successfully!"
EOF
