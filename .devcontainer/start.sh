#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .codespace

# Load optional Codespaces environment variables.
if [ -f .env ]; then
  set -a
  . .env
  set +a
fi

export SNCK_PANEL_PORT="${SNCK_PANEL_PORT:-5000}"
export SNCK_PANEL_SECRET="${SNCK_PANEL_SECRET:-codespace-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
export SNCK_CODESPACE="1"

# Ensure the same virtual environment used by setup.sh exists.
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

# Start/restart the panel without requiring a terminal session to stay open.
pkill -f 'python.*snck_panel.py' 2>/dev/null || true
nohup .venv/bin/python snck_panel.py >.codespace/panel.log 2>&1 &
PANEL_PID=$!

# Start the Discord bot when a token is supplied through the Codespaces secret/env.
if [ -n "${DISCORD_TOKEN:-}" ]; then
  pkill -f 'python.*launcher.py' 2>/dev/null || true
  nohup .venv/bin/python launcher.py >.codespace/bot.log 2>&1 &
fi

sleep 2
if ! kill -0 "$PANEL_PID" 2>/dev/null; then
  cat .codespace/panel.log
  exit 1
fi

# devcontainer.json forwards this port automatically.
echo "Snck KVM Panel: http://localhost:${SNCK_PANEL_PORT}"
echo "Codespaces: port ${SNCK_PANEL_PORT} is configured for automatic forwarding."
if [ -n "${DISCORD_TOKEN:-}" ]; then
  echo "Snck Discord Bot: ONLINE/STARTING"
else
  echo "Snck Discord Bot: DISCORD_TOKEN is not configured"
fi
