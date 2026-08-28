@echo off
REM laptop-guard setup launcher - double-click to open the Settings window.
REM Installs dependencies on first run, then opens the settings GUI.
cd /d "%~dp0"
echo Installing dependencies (only needed once)...
python -m pip install -r requirements.txt
python guard_setup.py
if errorlevel 1 (
    echo.
    echo [Guard] Setup exited with an error. Make sure Python is installed
    echo [Guard] and added to PATH, then try again.
)
pause
