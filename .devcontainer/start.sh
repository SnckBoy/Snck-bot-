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

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

if [ ! -f snck_panel_fixed.py ]; then
  echo 'snck_panel_fixed.py is missing.' >&2
  exit 1
fi
cp -f snck_panel_fixed.py snck_panel.py
.venv/bin/python -m py_compile snck_panel.py

pkill -f 'python.*snck_panel.py' 2>/dev/null || true
nohup .venv/bin/python snck_panel.py >.codespace/panel.log 2>&1 &
PANEL_PID=$!

sleep 2
if ! kill -0 "$PANEL_PID" 2>/dev/null; then
  cat .codespace/panel.log
  exit 1
fi

if ! curl -fsS --max-time 5 "http://127.0.0.1:${SNCK_PANEL_PORT}/health" >/dev/null; then
  cat .codespace/panel.log
  exit 1
fi

echo "Snck KVM Panel: http://localhost:${SNCK_PANEL_PORT}"
echo "Codespaces: port ${SNCK_PANEL_PORT} is configured for automatic forwarding."
echo "Panel health check: OK"
