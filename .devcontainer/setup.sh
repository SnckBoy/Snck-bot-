#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp -f snck_panel_fixed.py snck_panel.py
.venv/bin/python -m py_compile snck_panel_fixed.py snck_panel.py kvm.py
printf '%s\n' 'Snck Codespaces setup complete.'