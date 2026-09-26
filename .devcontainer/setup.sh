#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m py_compile snck_hvm_panel.py vps_service.py snck_panel.py kvm.py bot.py launcher.py snck_panel_bridge.py
printf '%s\n' 'Snck HVM Codespaces setup complete.'
