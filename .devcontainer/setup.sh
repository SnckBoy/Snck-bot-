#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Do not overwrite the canonical panel with the obsolete v2 implementation.
# The canonical snck_panel.py is the only panel entrypoint.
.venv/bin/python -m py_compile snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py
printf '%s\n' 'Snck Codespaces setup complete.'
