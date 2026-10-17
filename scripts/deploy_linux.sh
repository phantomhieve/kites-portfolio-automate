#!/bin/bash
set -e

# Default Server details (change as needed or pass via env vars)
SERVER_USER=${SERVER_USER:-"mobileci"}
SERVER_HOST=${SERVER_HOST:-"mac-mini"}
# Target the user's home directory
TARGET_DIR=${TARGET_DIR:-"/home/${SERVER_USER}/kites-automate"}
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

echo "Cleaning up previous installations..."
# Clean up the previous attempt in /opt and any existing folder in the home directory
ssh "${SSH_TARGET}" "sudo rm -rf /opt/kites-automate && rm -rf ${TARGET_DIR} && mkdir -p ${TARGET_DIR}"

echo "Deploying kites-automate to ${SSH_TARGET}:${TARGET_DIR}..."

# 1. Sync the current repository to the target server
echo "Syncing files..."
# Exclude both local virtual environments (.venv) and the old one (venv) from kites
rsync -avz --exclude '.git' --exclude '.venv' --exclude 'venv' --exclude '__pycache__' ./ "${SSH_TARGET}:${TARGET_DIR}/"

# 2. SSH and configure the server
echo "Configuring server requirements..."
ssh "${SSH_TARGET}" << EOF
  set -e
  
  echo "======================================"
  echo "Verifying Python version on server:"
  python3 --version
  echo "======================================"
  
  # Install OS dependencies
  echo "Installing system dependencies..."
  sudo apt-get update
  sudo apt-get install -y python3-venv python3-pip chromium-browser chromium-chromedriver
  
  # Set up Virtual Environment (Ubuntu 26.04 defaults to Python 3.14 — use 3.13 from deadsnakes when available)
  cd "${TARGET_DIR}"
  PYTHON_BIN=\$(command -v python3.13 2>/dev/null || command -v python3)
  echo "Using Python: \$(\$PYTHON_BIN -V)"
  echo "Setting up Python environment in ${TARGET_DIR}..."
  \$PYTHON_BIN -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  
  echo "======================================"
  echo "Code pushed and libraries installed successfully in ${TARGET_DIR}!"
  echo "Key Python libraries installed:"
  pip freeze | grep -E "selenium|kiteconnect" || true
  echo "======================================"
EOF
