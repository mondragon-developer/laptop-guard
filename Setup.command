#!/bin/bash
# laptop-guard setup launcher - double-click in Finder to open Settings.
# Installs dependencies on first run, then opens the settings GUI.
cd "$(dirname "$0")"

PYTHON_BIN="$(command -v python3 || command -v python)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[Guard] Python 3 not found. Install it from https://www.python.org"
    read -r -p "Press Enter to close..."
    exit 1
fi

echo "Installing dependencies (only needed once)..."
"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" guard_setup.py
echo
read -r -p "[Guard] Press Enter to close..."
