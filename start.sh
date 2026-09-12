#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$APP_DIR/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Snck virtual environment is missing. Run install.sh option 1 first."
  exit 1
fi
exec "$PYTHON" "$APP_DIR/launcher.py"
