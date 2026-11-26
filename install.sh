#!/usr/bin/env bash
# Ubuntu 22.04/24.04 (Oracle Cloud Always Free ARM ya koi bhi VPS) ke liye setup.
# Chalane se pehle: .env banao  ->  cp .env.example .env  ->  nano .env
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/opencode-telegram-bot}"
cd "$APP_DIR"

echo "==> system packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends curl ca-certificates git unzip python3 python3-venv python3-pip

echo "==> opencode install (user-local)"
if ! command -v opencode >/dev/null 2>&1; then
  curl -fsSL https://opencode.ai/install | bash
  export PATH="$HOME/.opencode/bin:$PATH"
fi
opencode --version

echo "==> python venv"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "==> workspace"
mkdir -p "$HOME/opencode-workspace"

if [ ! -f .env ]; then
  echo "!! .env nahi mila. Pehle 'cp .env.example .env' karke BOT_TOKEN aur ACCESS_CODE bharo, phir ye script dobara chalao."
  exit 1
fi

echo "==> systemd service"
sudo cp deploy/opencode-bot.service /etc/systemd/system/opencode-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now opencode-bot
sleep 3
sudo systemctl --no-pager status opencode-bot | head -20

echo
echo "Ho gaya. Log dekho:  tail -f $APP_DIR/bot.log"
echo "Telegram me bot ko /start YOUR_CODE bhejo."
