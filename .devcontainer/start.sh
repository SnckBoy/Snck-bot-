#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p .codespace

if [ -f .env ]; then
  set -a
  . .env
  set +a
fi

export SNCK_PANEL_PORT="${SNCK_PANEL_PORT:-5000}"
export SNCK_PANEL_SECRET="${SNCK_PANEL_SECRET:-codespace-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
export SNCK_CODESPACE="1"
export SNCK_PANEL_HOST="0.0.0.0"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

# Stop only the previous panel process; the bracket prevents pkill from matching itself.
pkill -f '[s]nck_panel.py' 2>/dev/null || true
nohup .venv/bin/python snck_panel.py >.codespace/panel.log 2>&1 &
PANEL_PID=$!

for _ in $(seq 1 20); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${SNCK_PANEL_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! kill -0 "$PANEL_PID" 2>/dev/null; then
  cat .codespace/panel.log
  exit 1
fi

if ! curl -fsS --max-time 3 "http://127.0.0.1:${SNCK_PANEL_PORT}/health" >/dev/null 2>&1; then
  echo 'Snck panel process exists but /health is not responding.'
  cat .codespace/panel.log
  exit 1
fi

echo "Snck KVM Panel: http://127.0.0.1:${SNCK_PANEL_PORT}"
echo "Codespaces: port ${SNCK_PANEL_PORT} is configured for automatic HTTP forwarding."

if [ -n "${DISCORD_TOKEN:-}" ]; then
  pkill -f '[l]auncher.py' 2>/dev/null || true
  nohup .venv/bin/python launcher.py >.codespace/bot.log 2>&1 &
  echo 'Snck Discord Bot: STARTING'
else
  echo 'Snck Discord Bot: DISCORD_TOKEN is not configured'
fi
