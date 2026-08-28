#!/bin/bash
# laptop-guard launcher - double-click in Finder to start the app.
# The app handles first-time setup, dependency checks, and activation.
# Opens in Terminal so macOS can request Accessibility/Camera permissions
# for the terminal app on first run.
cd "$(dirname "$0")"

PYTHON_BIN="$(command -v python3 || command -v python)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[Guard] Python 3 not found. Install it from https://www.python.org"
    read -r -p "Press Enter to close..."
    exit 1
fi

"$PYTHON_BIN" guard_app.py
echo
read -r -p "[Guard] Press Enter to close..."
