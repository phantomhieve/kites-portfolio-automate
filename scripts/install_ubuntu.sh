#!/usr/bin/env bash
set -euo pipefail

# Create service user
if ! id -u kites >/dev/null 2>&1; then
  sudo useradd -r -s /usr/sbin/nologin -d /opt/kites-automate kites
fi

sudo apt-get update -y
sudo apt-get install -y python3.10-venv python3-pip systemd tzdata

install_dir=/opt/kites-automate
sudo mkdir -p "$install_dir"
sudo chown -R kites:kites "$install_dir"

# Create venv and install deps
sudo -u kites bash -c "cd $install_dir && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# Install systemd units
sudo mkdir -p /etc/systemd/system
sudo cp deploy/systemd/kites-automate.service /etc/systemd/system/
sudo cp deploy/systemd/kites-automate.timer /etc/systemd/system/
sudo cp deploy/systemd/kites-automate-rotate.service /etc/systemd/system/
sudo cp deploy/systemd/kites-automate-rotate.timer /etc/systemd/system/

sudo systemctl daemon-reload

cat <<EOF
Installation complete.
1) Place .env at $install_dir/.env
2) Enable timers:
   sudo systemctl enable --now kites-automate.timer
   sudo systemctl enable --now kites-automate-rotate.timer
EOF
