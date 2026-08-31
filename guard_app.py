"""
guard_app.py - single-icon launcher for laptop-guard.

Double-click flow:
  - first run ever: asks whether to keep the default settings or
    customize them (phone number, secret combo, alarm/clip times), then
    saves and activates.
  - every later run: a short countdown splash, then the guard activates
    on its own. The "Settings" button on the splash is the way back into
    the settings - they are never shown again unless requested.
  - missing dependencies are installed automatically before anything
    else happens.
  - on macOS, the Accessibility permission (required so the guard can
    see and block input) is checked up front, with instructions if the
    grant is missing.

Launched without a console on Windows (pythonw.exe shortcut); on macOS
it runs inside Terminal via LaptopGuard.command, which is what holds
the Accessibility/Camera permission grants.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

HERE = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)          # PyInstaller build
    else os.path.dirname(os.path.abspath(__file__))
)
os.chdir(HERE)

_COUNTDOWN_SEC = 5
_ICON = os.path.join(HERE, "icon.ico")        # Windows: window + shortcut
_ICON_PNG = os.path.join(HERE, "icon.png")    # macOS/Linux window icon


def _mac_accessibility_ok() -> bool:
    """On macOS, check that the host app holds the Accessibility grant
    (required for pynput to see and block input). Anywhere else, or when
    the check itself fails, report True so the user is never blocked."""
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework"
            "/ApplicationServices")
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True


def _apply_icon(root: tk.Tk) -> None:
    """Best-effort window icon: .ico on Windows, .png elsewhere."""
    try:
        if sys.platform.startswith("win") and os.path.exists(_ICON):
            root.iconbitmap(_ICON)
        elif os.path.exists(_ICON_PNG):
            root.iconphoto(True, tk.PhotoImage(file=_ICON_PNG))
    except tk.TclError:
        pass


def _safe_destroy(root: tk.Tk) -> None:
    """Destroy the window; harmless if the user already closed it."""
    try:
        root.destroy()
    except tk.TclError:
        pass


def _silence_stdio() -> None:
    """pythonw.exe has no console; print() would crash without this."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def _ensure_deps(status: tk.Label) -> bool:
    """Install anything missing from requirements.txt via pip.

    In a frozen (PyInstaller) build every dependency is already bundled
    and there is no pip, so the check is skipped entirely.
    """
    if getattr(sys, "frozen", False):
        return True
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    modules = {"pynput": "pynput", "numpy": "numpy",
               "pygame": "pygame", "cv2": "opencv-python"}
    missing = [pkg for mod, pkg in modules.items()
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return True
    status.config(text="Installing components (one time only)...")
    status.update_idletasks()
    res = subprocess.run(
        [sys.executable, "-m", "pip", "install", *missing],
        capture_output=True, text=True)
    if res.returncode != 0:
        messagebox.showerror(
            "Setup failed",
            "Could not install: " + ", ".join(missing) +
            "\n\nCheck the internet connection and try again.")
        return False
    return True


def main() -> None:
    _silence_stdio()
    from laptop_guard import (CONFIG_FILE, GuardConfig, LaptopGuard,
                              load_config, save_config)
    from guard_setup import SettingsForm

    root = tk.Tk()
    root.title("Laptop Guard")
    root.resizable(False, False)
    _apply_icon(root)

    status = tk.Label(root, text="Checking components...",
                      padx=30, pady=25)
    status.pack()
    root.update_idletasks()
    if not _ensure_deps(status):
        _safe_destroy(root)
        return

    if not _mac_accessibility_ok():
        if not messagebox.askokcancel(
                "Accessibility permission needed",
                "macOS has not granted Accessibility access to this\n"
                "terminal, so the guard cannot watch or block the\n"
                "keyboard and mouse.\n\n"
                "To fix: System Settings -> Privacy & Security ->\n"
                "Accessibility, enable this terminal, then quit and\n"
                "reopen it.\n\n"
                "Press OK to activate anyway (not recommended)."):
            _safe_destroy(root)
            return

    go = {"activate": False}
    ui = {"cancelled": False}        # countdown stopped (e.g. in Settings)

    def _activate() -> None:
        go["activate"] = True
        root.quit()

    def _clear() -> None:
        for widget in root.winfo_children():
            widget.destroy()

    def _show_form() -> None:
        ui["cancelled"] = True       # stop the countdown, if any
        _clear()
        tk.Label(root, text="Laptop Guard - Settings",
                 font=("Arial", 12, "bold")).pack(pady=(12, 0))
        SettingsForm(root, on_saved=_activate).pack(padx=6, pady=6)
        tk.Label(root, text="Saving activates the guard.",
                 fg="#555").pack(pady=(0, 10))

    def _first_run() -> None:
        _clear()
        defaults = GuardConfig()
        tk.Label(root, text="Welcome to Laptop Guard",
                 font=("Arial", 12, "bold")).pack(pady=(14, 4))
        tk.Label(
            root,
            text="Default settings:\n"
                 f"Secret combo: {'+'.join(defaults.key_combo).upper()}\n"
                 f"Phone on warning screen: {defaults.phone}\n"
                 f"Alarm: {defaults.alarm_duration_sec} s   "
                 f"Webcam clip: {defaults.record_seconds} s",
            justify="center").pack(pady=4)
        btns = tk.Frame(root)
        btns.pack(pady=10)

        def _use_defaults() -> None:
            # writing the file marks setup as done: this screen is
            # never shown again
            save_config({
                "phone": defaults.phone,
                "key_combo": list(defaults.key_combo),
                "alarm_duration_sec": defaults.alarm_duration_sec,
                "record_seconds": defaults.record_seconds,
            })
            _activate()

        tk.Button(btns, text="Use defaults and activate",
                  width=22, default="active",
                  command=_use_defaults).pack(side="left", padx=6)
        tk.Button(btns, text="Customize...",
                  width=14, command=_show_form).pack(side="left", padx=6)

    def _countdown() -> None:
        _clear()
        lbl = tk.Label(root, padx=30)
        lbl.pack(pady=(16, 4))
        btns = tk.Frame(root)
        btns.pack(pady=10)
        tk.Button(btns, text="Activate now", width=14, default="active",
                  command=_activate).pack(side="left", padx=6)
        tk.Button(btns, text="Settings", width=12,
                  command=_show_form).pack(side="left", padx=6)

        remaining = {"n": _COUNTDOWN_SEC}

        def _tick() -> None:
            if go["activate"] or ui["cancelled"]:
                return
            if remaining["n"] <= 0:
                _activate()
                return
            lbl.config(
                text=f"Activating in {remaining['n']} s...\n"
                     "Click Settings only if you want to change anything.")
            remaining["n"] -= 1
            root.after(1000, _tick)

        _tick()

    if os.path.exists(CONFIG_FILE):
        _countdown()
    else:
        _first_run()

    root.mainloop()
    _safe_destroy(root)
    if go["activate"]:
        LaptopGuard(load_config()).activate()


if __name__ == "__main__":
    main()
