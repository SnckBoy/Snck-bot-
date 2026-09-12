#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .codespace
if [ -f .env ]; then set -a; . .env; set +a; fi
export SNCK_PANEL_PORT="${SNCK_PANEL_PORT:-5000}"
export SNCK_PANEL_SECRET="${SNCK_PANEL_SECRET:-codespace-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
export SNCK_CODESPACE="1"
# Keep the panel in the foreground so Codespaces can supervise it.
pkill -f 'snck_panel.py' 2>/dev/null || true
nohup .venv/bin/python snck_panel.py >.codespace/panel.log 2>&1 &
PANEL_PID=$!
if [ -n "${DISCORD_TOKEN:-}" ]; then
  pkill -f 'launcher.py' 2>/dev/null || true
  nohup .venv/bin/python launcher.py >.codespace/bot.log 2>&1 &
fi
sleep 2
if ! kill -0 "$PANEL_PID" 2>/dev/null; then
  cat .codespace/panel.log
  exit 1
fi
echo "Snck KVM Panel: http://localhost:${SNCK_PANEL_PORT}"
echo "Codespaces will automatically forward port ${SNCK_PANEL_PORT}."
if [ -n "${DISCORD_TOKEN:-}" ]; then echo "Snck Discord Bot: starting from DISCORD_TOKEN secret."; else echo "Discord bot: DISCORD_TOKEN is not configured in this Codespace."; fi
