#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Use the same canonical panel as the Ubuntu installer.
cp -f snck_panel_v2.py snck_panel.py
.venv/bin/python patch_panel_bot_setup.py
.venv/bin/python -m py_compile snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py
printf '%s\n' 'Snck Codespaces setup complete.'
