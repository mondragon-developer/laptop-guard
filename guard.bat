@echo off
REM laptop-guard launcher - double-click to activate the guard.
REM Runs the script with the console visible so status and log messages show.
cd /d "%~dp0"
python laptop_guard.py
if errorlevel 1 (
    echo.
    echo [Guard] The script exited with an error. If Python or a dependency is
    echo [Guard] missing, run:  pip install -r requirements.txt
)
pause
