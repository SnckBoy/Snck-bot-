#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p .codespace
if [ -f .env ]; then set -a; . .env; set +a; fi
export SNCK_PANEL_PORT="${SNCK_PANEL_PORT:-5000}"
export SNCK_PANEL_SECRET="${SNCK_PANEL_SECRET:-codespace-$(python3 -c 'import secrets; print(secrets.token_hex(24))')}"
export SNCK_CODESPACE="1"
export SNCK_PANEL_HOST="0.0.0.0"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; .venv/bin/python -m pip install --upgrade pip; .venv/bin/pip install -r requirements.txt; fi
if [ -f .codespace/panel.pid ]; then old_pid="$(cat .codespace/panel.pid 2>/dev/null || true)"; if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then kill "$old_pid" 2>/dev/null || true; fi; rm -f .codespace/panel.pid; fi
: > .codespace/panel.log
nohup .venv/bin/python snck_hvm_panel.py >.codespace/panel.log 2>&1 &
PANEL_PID=$!; echo "$PANEL_PID" > .codespace/panel.pid
ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "$PANEL_PID" 2>/dev/null; then break; fi
  if curl -fsS --max-time 2 "http://127.0.0.1:${SNCK_PANEL_PORT}/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then echo 'Snck HVM panel failed to start.' >&2; cat .codespace/panel.log >&2 || true; exit 1; fi
echo "Snck HVM Panel: http://127.0.0.1:${SNCK_PANEL_PORT}"
echo "Codespaces: port ${SNCK_PANEL_PORT} is configured for automatic HTTP forwarding."
if [ -n "${DISCORD_TOKEN:-}" ]; then
  if [ -f .codespace/bot.pid ]; then old_bot="$(cat .codespace/bot.pid 2>/dev/null || true)"; if [[ "$old_bot" =~ ^[0-9]+$ ]] && kill -0 "$old_bot" 2>/dev/null; then kill "$old_bot" 2>/dev/null || true; fi; rm -f .codespace/bot.pid; fi
  : > .codespace/bot.log; nohup .venv/bin/python launcher.py >.codespace/bot.log 2>&1 & echo $! > .codespace/bot.pid; echo 'Snck Discord Bot: STARTING'
else echo 'Snck Discord Bot: DISCORD_TOKEN is not configured'; fi
