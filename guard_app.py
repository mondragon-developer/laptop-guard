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
    see and block input) is requested from macOS up front and the splash
    waits until it has been granted.

Launched without a console on Windows (pythonw.exe shortcut). On macOS
there are two supported flows: the frozen LaptopGuard.app from the release
zip, and the source checkout run inside Terminal via LaptopGuard.command.
Whichever host is used is the one that must hold the Accessibility/Camera
permission grants.

A frozen build has no console, so prints, tracebacks and the input
helper's own output go to guard_debug.log in the data folder.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import traceback
import tkinter as tk
from tkinter import messagebox

from laptop_guard import DEBUG_LOG, INPUT_HELPER_ARG, app_dir, log_debug

# Working directory for runtime files (config, log, webcam clip). On a
# frozen macOS build this is ~/Library/Application Support/LaptopGuard,
# because the .app itself may run from a read-only translocated path.
HERE = app_dir()
os.makedirs(HERE, exist_ok=True)
os.chdir(HERE)

_COUNTDOWN_SEC = 5
_ICON = os.path.join(HERE, "icon.ico")        # Windows: window + shortcut
_ICON_PNG = os.path.join(HERE, "icon.png")    # macOS/Linux window icon
_AX_SETTINGS_URL = ("x-apple.systempreferences:com.apple.preference.security"
                    "?Privacy_Accessibility")


def _ax_trusted(prompt: bool = False) -> bool:
    """macOS: may this process watch and block input?

    prompt=True additionally makes macOS add the app to the Accessibility
    list and open its own "would like to control this computer" dialog;
    the call still returns the current state without waiting for it.
    Anywhere else, or when the check is unavailable, report True so a
    broken check never locks the user out.
    """
    if sys.platform != "darwin":
        return True
    try:
        import HIServices    # pyobjc, always installed next to pynput
    except ImportError:
        return True
    try:
        if prompt:
            key = getattr(HIServices, "kAXTrustedCheckOptionPrompt",
                          "AXTrustedCheckOptionPrompt")
            return bool(HIServices.AXIsProcessTrustedWithOptions({key: True}))
        return bool(HIServices.AXIsProcessTrusted())
    except Exception as exc:
        log_debug(f"accessibility check failed: {exc}")
        return True


def _open_ax_settings() -> None:
    try:
        subprocess.Popen(["open", _AX_SETTINGS_URL])
    except OSError as exc:
        log_debug(f"could not open System Settings: {exc}")


def _wait_for_accessibility(root: tk.Tk) -> bool:
    """Hold the splash until macOS trusts this app; False if the user quits.

    Checking alone is not enough: the app only appears in the
    Accessibility list once it has asked, and pynput's listener simply
    returns when the event tap is refused, so an unchecked grant used to
    end as a silent exit right after the user turned it on.
    """
    if _ax_trusted():
        return True
    _ax_trusted(prompt=True)
    log_debug("accessibility not granted yet; waiting")
    for widget in root.winfo_children():
        widget.destroy()
    tk.Label(root, text="Permission needed",
             font=("Arial", 12, "bold")).pack(pady=(14, 4))
    tk.Label(
        root, justify="left",
        text="Laptop Guard needs Accessibility access to watch and block\n"
             "the keyboard and mouse.\n\n"
             "1. macOS just asked for it. Click \"Open System Settings\".\n"
             "2. In Privacy & Security -> Accessibility, turn on LaptopGuard\n"
             "   (Terminal instead, if you started the app from Terminal).\n"
             "3. Switch already on but this window not moving? The entry\n"
             "   belongs to an older copy and its switch does nothing:\n"
             "   select LaptopGuard, press -, then reopen this app and\n"
             "   accept the fresh request. Normal after every update.\n\n"
             "This window continues by itself once access is granted.",
    ).pack(padx=20, pady=4)
    btns = tk.Frame(root)
    btns.pack(pady=(10, 2))
    tk.Button(btns, text="Open System Settings", width=20,
              command=_open_ax_settings).pack(side="left", padx=6)
    tk.Button(btns, text="Quit", width=10,
              command=root.quit).pack(side="left", padx=6)

    state = {"granted": False, "done": False, "polls": 0}

    def _try_anyway() -> None:
        # safe now that a refused tap ends on the explanation screen; the
        # helper's tap attempt also re-registers the app with macOS
        log_debug("accessibility wait skipped by user (Try anyway)")
        state["granted"] = True
        state["done"] = True
        root.quit()

    tk.Button(root, text="Try anyway", width=12,
              command=_try_anyway).pack(pady=(0, 4))
    wait_lbl = tk.Label(root, fg="#555",
                        text="Waiting for macOS to report access...")
    wait_lbl.pack(pady=(0, 10))

    def _poll() -> None:
        if state["done"]:
            return
        if _ax_trusted():
            state["granted"] = True
            state["done"] = True
            log_debug(f"accessibility granted after {state['polls']} s")
            root.quit()
            return
        state["polls"] += 1
        wait_lbl.config(
            text=f"macOS still reports access is off ({state['polls']} s).\n"
                 "Turned it on already? Remove the entry with - and reopen\n"
                 "the app, or press \"Try anyway\".")
        if state["polls"] % 15 == 0:
            log_debug(f"still waiting for accessibility ({state['polls']} s);"
                      " AXIsProcessTrusted is false")
        root.after(1000, _poll)

    root.after(1000, _poll)
    root.mainloop()
    state["done"] = True      # a pending _poll must not quit the next loop
    if not state["granted"]:
        log_debug("accessibility not granted; user quit")
    return state["granted"]


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


def _setup_stdio() -> None:
    """A windowed build has no console: route prints and tracebacks to
    guard_debug.log so a silent exit leaves a trace. Source runs keep
    their terminal; pythonw.exe (no streams at all) gets devnull."""
    if getattr(sys, "frozen", False):
        try:
            os.makedirs(os.path.dirname(DEBUG_LOG), exist_ok=True)
            fh = open(DEBUG_LOG, "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = fh
            return
        except OSError:
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def _report_crash(exc_type, exc, tb) -> None:
    """Unhandled exceptions: log the traceback and show it, instead of
    the window just vanishing."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log_debug("unhandled error:\n" + text)
    try:
        messagebox.showerror(
            "Laptop Guard error",
            f"{exc_type.__name__}: {exc}\n\nDetails: {DEBUG_LOG}")
    except Exception:
        pass


def _failure_text(reason: str) -> str:
    if reason == "accessibility":
        return ("macOS did not let Laptop Guard block the keyboard and\n"
                "mouse, so the guard switched itself off.\n\n"
                "Open System Settings -> Privacy & Security -> Accessibility.\n"
                "If LaptopGuard is listed, select it and press -. Then reopen\n"
                "the app and accept the request again. A stale entry is\n"
                "normal after installing a new version.\n\n"
                f"Details: {DEBUG_LOG}")
    return ("The input watcher stopped unexpectedly, so the guard\n"
            "switched itself off.\n\n"
            f"Details: {DEBUG_LOG}")


def _show_failure(root: tk.Tk, reason: str) -> None:
    """Shown in the (hidden) launcher window itself: a message box parented
    to a withdrawn window can end up invisible on macOS."""
    for widget in root.winfo_children():
        widget.destroy()
    tk.Label(root, text="Laptop Guard stopped",
             font=("Arial", 12, "bold")).pack(pady=(14, 4))
    tk.Label(root, text=_failure_text(reason),
             justify="left").pack(padx=20, pady=4)
    tk.Button(root, text="Close", width=10,
              command=root.quit).pack(pady=10)
    root.deiconify()
    root.lift()
    root.mainloop()


def _ensure_deps(status: tk.Label) -> bool:
    """Install anything missing from requirements.txt via pip.

    In a frozen (PyInstaller) build every dependency is already bundled
    and there is no pip, so the check is skipped entirely.
    """
    if getattr(sys, "frozen", False):
        return True
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    modules = {"pynput": "pynput", "numpy": "numpy", "cv2": "opencv-python"}
    if sys.platform != "win32":
        modules["pygame"] = "pygame"
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
    importlib.invalidate_caches()    # the fresh packages import in-process
    return True


def main() -> None:
    from guard_runtime.version import VERSION
    from guard_runtime.displays import enable_dpi_awareness
    enable_dpi_awareness()
    if "--check" in sys.argv[1:]:
        # Hardware-free smoke check, including in the packaged executable.
        import json
        from guard_runtime.storage import RuntimePaths
        from guard_runtime.video import VideoRing
        from guard_runtime.system_events import parse_events
        from guard_runtime.auto_guard import IDLE_SECONDS
        from laptop_guard import load_config
        load_config()
        parse_events("<Events/>")
        paths = RuntimePaths()
        result = {"status": "ok", "version": VERSION, "data": str(paths.root),
                  "logs": str(paths.logs), "videos": str(paths.videos),
                  "config": os.path.join(HERE, "guard_config.json"),
                  "automatic_idle_seconds": IDLE_SECONDS}
        if "--check-output" in sys.argv:
            output = sys.argv[sys.argv.index("--check-output") + 1]
            with open(output, "w", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2)
        elif sys.stdout:
            print(json.dumps(result, indent=2))
        return
    if INPUT_HELPER_ARG in sys.argv[1:]:
        # macOS helper process respawned by InputGuard: run the pynput
        # listeners on this process's main thread and report events on
        # stdout (macOS 26 kills pynput's listener on background threads).
        # Must run before any tkinter window is created.
        from laptop_guard import input_helper_main
        input_helper_main()
        return
    _setup_stdio()
    sys.excepthook = _report_crash
    # exe path shows whether macOS runs the app translocated (read-only
    # quarantine copy), which matters when debugging permission grants
    log_debug(f"launcher start: frozen={getattr(sys, 'frozen', False)} "
              f"exe={sys.executable} data={HERE}")
    from laptop_guard import (CONFIG_FILE, GuardConfig, LaptopGuard,
                              load_config, save_config)
    from guard_setup import SettingsForm

    if "--test" in sys.argv:
        from guard_runtime.diagnostics import show
        root = tk.Tk()
        status = tk.Label(root, text="Comprobando componentes…")
        status.pack(padx=25, pady=20)
        if _ensure_deps(status):
            show(root, load_config())
        else:
            _safe_destroy(root)
        return

    if any(mode in sys.argv for mode in ("--watch", "--auto-settings", "--activate-idle")):
        if sys.platform != "win32":
            raise RuntimeError("Automatic idle activation is currently Windows-only")
        from guard_runtime.auto_guard import AutoWatcher, controls, eligible
        from guard_runtime.idle import WindowsIdle
        from guard_runtime.storage import RuntimePaths
        if "--activate-idle" in sys.argv:
            paths, detector = RuntimePaths(), WindowsIdle()
            if not os.path.exists(CONFIG_FILE) or not eligible(paths, detector):
                return
            root = tk.Tk()
            root.withdraw()
            try:
                failure = LaptopGuard(load_config(), root=root).activate(
                    activation_reason="idle", can_activate=lambda: eligible(paths, detector))
                if failure:
                    log_debug(f"automatic activation failed: {failure}")
            finally:
                _safe_destroy(root)
            return
        root = tk.Tk()
        if "--auto-settings" in sys.argv:
            controls(root)
        else:
            AutoWatcher(root).run()
        return

    root = tk.Tk()
    root.title(f"Laptop Guard {VERSION}")
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", root.quit)   # closing never activates
    root.report_callback_exception = _report_crash  # button callbacks too
    _apply_icon(root)

    status = tk.Label(root, text="Checking components...",
                      padx=30, pady=25)
    status.pack()
    root.update_idletasks()
    if not _ensure_deps(status):
        _safe_destroy(root)
        return
    if not _wait_for_accessibility(root):
        _safe_destroy(root)
        return

    go = {"activate": False, "test": False, "automatic": False}
    ui = {"cancelled": False}        # countdown stopped (e.g. in Settings)

    def _activate() -> None:
        go["activate"] = True
        root.quit()

    def _test() -> None:
        ui["cancelled"] = True
        go["test"] = True
        root.quit()

    def _automatic() -> None:
        ui["cancelled"] = True
        go["automatic"] = True
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
        tk.Button(root, text="Probar sin bloquear", command=_test).pack(pady=(0, 12))

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
        tk.Button(root, text="Probar sin bloquear", command=_test).pack(pady=(0, 12))
        if sys.platform == "win32":
            tk.Button(root, text="Automático (15 minutos)", command=_automatic).pack(pady=(0, 12))

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
    if go["automatic"]:
        from guard_runtime.auto_guard import controls
        _clear()
        controls(root)
        return
    if go["test"]:
        from guard_runtime.diagnostics import show
        show(root, load_config())
        return
    if not go["activate"]:
        _safe_destroy(root)
        return

    # The root stays alive (hidden) and later hosts the warning screen.
    # Destroying it and creating a second Tk root crashes on macOS: Tk
    # Aqua keeps a stale pointer to the first interpreter of the process
    # (Tk ticket c18c36f8, cpython issue 123204).
    root.withdraw()
    failure = LaptopGuard(load_config(), root=root).activate()
    if failure:
        _show_failure(root, failure)


if __name__ == "__main__":
    main()
