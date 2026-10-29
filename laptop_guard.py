"""
laptop_guard.py Simple laptop "protection" guard.

• Launch the script to ACTIVATE; press your combo (default Ctrl+Shift+Z) to DEACTIVATE.
• While active, ANY other key or mouse input triggers:
    -a full-screen black warning window (fake ransom message),
    -a loud alarm for the configured duration,
    -system-wide input suppression (keystrokes/clicks never reach the OS),
    -a timestamped entry in the intrusion log,
    -a short webcam clip of the intruder (if opencv-python is installed),
    -sleep/hibernate prevention (Windows).
• Only the correct combo dismisses everything and restores normal use.
  (Ctrl+Alt+Del always remains available as an OS-level escape hatch.)

Design notes (SOLID + KISS):
  S        - each class has one job (config, alarm, screen, power, input, orchestrator)
  O/Closed - swap AlarmPlayer / PowerManager implementations without editing callers
  Liskov   - any AlarmPlayer subclass is interchangeable
  I        - tiny interfaces (play/stop, show/deactivate, prevent/restore)
  D        - LaptopGuard depends on abstractions, not concrete classes
  KISS     - stdlib tkinter for the screen; no GUI framework bloat
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
import time
import tkinter as tk
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from guard_runtime.storage import RuntimePaths, InstanceLock, app_dir
from guard_runtime.audit import AuditLog
from guard_runtime.system_events import SystemEvents
from guard_runtime.video import WebcamRecorder


# ──────────────────────────────────────────────
# 1. CONFIGURATION  (Single Responsibility)
# ──────────────────────────────────────────────
CONFIG_FILE = os.path.join(app_dir(), "guard_config.json")
DEBUG_LOG = str(RuntimePaths().logs / "guard_debug.log")


def log_debug(msg: str) -> None:
    """Append a timestamped line to guard_debug.log; echoed to stderr
    unless stderr already is that file (frozen builds redirect it)."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    try:
        os.makedirs(os.path.dirname(DEBUG_LOG), exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    err = sys.stderr
    if err is not None and getattr(err, "name", None) != DEBUG_LOG:
        print(line, file=err)

MESSAGE_TEMPLATE = (
    "⚠️  SYSTEM BREACH DETECTED  ⚠️\n\n"
    "Call {phone} IMMEDIATELY.\n\n"
    "Do NOT turn off the computer."
)


@dataclass
class GuardConfig:
    """Runtime settings. Edit them with guard_setup.py (stored in
    guard_config.json); these defaults apply when no file exists."""

    key_combo: tuple[str, ...] = ("ctrl", "shift", "z")
    phone: str = "555-0100"          # placeholder - set your own in Settings
    message: str = ""                  # built from phone when left empty
    alarm_duration_sec: int = 90       # how long the alarm plays
    record_seconds: int = 5            # webcam clip length; 0 disables recording
    alarm_style: str = "siren"         # classic square-wave alarm, or gentler beeps
    flash_warning: bool = True
    show_simulation: bool = True       # two-minute visual effect only
    matrix_background: bool = True    # bounded, low-rate digital rain

    def __post_init__(self) -> None:
        if self.alarm_style not in ("siren", "beep"):
            self.alarm_style = "siren"
        if not self.message:
            self.message = MESSAGE_TEMPLATE.format(phone=self.phone)


# accepted modifier spellings in the setup window / config file
_MOD_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "shift": "shift",
    "alt": "alt", "option": "alt",
    "cmd": "cmd", "command": "cmd", "meta": "cmd", "win": "cmd",
}


def normalize_combo(text: str) -> tuple[str, ...]:
    """Parse 'ctrl+shift+z' style text into a normalized combo tuple.

    Raises ValueError unless the combo is one or more modifiers plus
    exactly one regular key - a bare modifier or a bare key is too easy
    to press by accident.
    """
    parts = [p.strip().lower() for p in text.replace(",", "+").split("+")]
    parts = [p for p in parts if p]
    mods: list[str] = []
    keys: list[str] = []
    for part in parts:
        if part in _MOD_ALIASES:
            mod = _MOD_ALIASES[part]
            if mod not in mods:
                mods.append(mod)
        else:
            keys.append(part)
    if not mods or len(keys) != 1:
        raise ValueError(
            "Combo must be one or more modifiers plus one key, "
            "e.g. ctrl+shift+z"
        )
    return tuple(mods + keys)


def load_config(path: str = CONFIG_FILE) -> GuardConfig:
    """Build a GuardConfig from guard_config.json; defaults if missing
    or malformed in any way (a broken file must never stop the guard)."""
    defaults = GuardConfig()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("top level must be an object")
        combo = data.get("key_combo")
        if not isinstance(combo, list) or not combo:
            combo = list(defaults.key_combo)
        return GuardConfig(
            key_combo=tuple(str(k).lower() for k in combo),
            phone=str(data.get("phone", defaults.phone)),
            alarm_duration_sec=int(data.get("alarm_duration_sec",
                                            defaults.alarm_duration_sec)),
            record_seconds=int(data.get("record_seconds",
                                        defaults.record_seconds)),
            alarm_style=str(data.get("alarm_style", defaults.alarm_style)),
            flash_warning=data.get("flash_warning", defaults.flash_warning) is not False,
            show_simulation=data.get("show_simulation", defaults.show_simulation) is not False,
            matrix_background=data.get("matrix_background", defaults.matrix_background) is not False,
        )
    except (OSError, ValueError, TypeError):
        return defaults


def save_config(data: dict, path: str = CONFIG_FILE) -> None:
    """Persist the settings dict written by guard_setup.py."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


# ──────────────────────────────────────────────
# 2. ALARM  (Open/Closed - swap implementations)
# ──────────────────────────────────────────────
class AlarmPlayer(ABC):
    @abstractmethod
    def play(self, duration_sec: int) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


class PygameAlarm(AlarmPlayer):
    """Classic alarm or alternating tones through the Mac audio backend."""

    def __init__(self, style="siren") -> None:
        # hide pygame's "Hello from the pygame community" banner so the
        # console stays clean (must be set before the pygame import)
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame  # noqa - deferred so import errors surface at use-time
        self._pygame = pygame
        self._style = style
        self._sound = None     # MUST keep a reference (see play())
        self._fallback = None
        self._stop = threading.Event()
        self._play_lock = threading.Lock()
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

    def play(self, duration_sec: int) -> None:
        try:
            if self._stop.is_set():
                return
            from guard_runtime.audio import pcm_tone
            # Keep the Sound in self._sound: pygame stops playback as soon
            # as the Sound object is garbage-collected, which is exactly
            # what made the alarm "sound once and stop" before.
            pcm = pcm_tone(self._style)
            with self._play_lock:
                if self._stop.is_set():
                    return
                self._sound = self._pygame.mixer.Sound(buffer=pcm)
                self._sound.set_volume(1.0)
                # loops counts REPEATS after the first play, hence the -1
                self._sound.play(loops=max(0, duration_sec - 1))  # 1 s per loop
        except Exception as exc:
            # never leave the guard silent: degrade to the winsound beeper
            print(f"  [Guard] pygame alarm failed: {exc}", file=sys.stderr)
            try:
                self._fallback = WinsoundAlarm()
                if not self._stop.is_set():
                    self._fallback.play(duration_sec)
            except Exception as exc2:
                print(f"  [Guard] winsound fallback failed: {exc2}",
                      file=sys.stderr)

    def stop(self) -> None:
        try:
            self._stop.set()
            if self._fallback:
                self._fallback.stop()
            with self._play_lock:
                if self._sound is not None:
                    self._sound.stop()
                    self._sound = None
                self._pygame.mixer.stop()
        except Exception as exc:
            print(f"  [Guard] alarm stop failed: {exc}", file=sys.stderr)


class WinsoundAlarm(AlarmPlayer):
    """Windows alarm, without an additional audio library."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def play(self, duration_sec: int) -> None:
        import winsound
        end = time.monotonic() + duration_sec
        while time.monotonic() < end and not self._stop.is_set():
            winsound.Beep(800, 150)
            if self._stop.is_set() or time.monotonic() >= end:
                break
            winsound.Beep(1200, 150)

    def stop(self) -> None:
        self._stop.set()


class WindowsSirenAlarm(WinsoundAlarm):
    """Loop the original square-wave tone with Windows' built-in WAV player."""

    def __init__(self):
        super().__init__()
        self._play_lock = threading.Lock()
        self._playing = False

    def _stop_sound(self):
        import winsound
        with self._play_lock:
            if self._playing:
                winsound.PlaySound(None, 0)
                self._playing = False

    def play(self, duration_sec):
        if self._stop.is_set() or duration_sec <= 0:
            return
        import tempfile
        import winsound
        from pathlib import Path
        from guard_runtime.audio import write_alarm
        try:
            with tempfile.TemporaryDirectory(prefix="laptop-guard-alarm-") as folder:
                path = Path(folder) / "alarm.wav"
                write_alarm(path)
                try:
                    with self._play_lock:
                        if self._stop.is_set():
                            return
                        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
                        self._playing = True
                    self._stop.wait(duration_sec)
                finally:
                    self._stop_sound()
        except Exception as exc:
            log_debug(f"Classic alarm failed; using beeps: {exc}")
            super().play(duration_sec)

    def stop(self):
        self._stop.set()
        self._stop_sound()


class _SilentAlarm(AlarmPlayer):
    """Last-resort fallback when neither pygame nor winsound is available."""

    def play(self, duration_sec: int) -> None: ...
    def stop(self) -> None: ...


def _make_alarm(style="siren") -> AlarmPlayer:
    """Factory - Dependency Inversion: caller gets an abstraction."""
    if platform.system().lower() == "windows":
        return WinsoundAlarm() if style == "beep" else WindowsSirenAlarm()
    try:
        return PygameAlarm(style)
    except Exception as exc:
        print(f"  [Guard] pygame unavailable ({exc}); alarm disabled",
              file=sys.stderr)
        return _SilentAlarm()


# ──────────────────────────────────────────────
# 3. FAKE SCREEN  (Single Responsibility)
# ──────────────────────────────────────────────
class FakeScreen:
    """One warning per Windows monitor; reuse the existing Tk interpreter."""

    def __init__(self, config: GuardConfig,
                 root: Optional[tk.Tk] = None) -> None:
        self._config = config
        self._root = root
        self._deactivate_evt = threading.Event()   # thread-safe signal

    def show(self, should_close=None, preview_seconds=None) -> None:
        """Main thread only. Preview permits Esc/click and always times out."""
        from guard_runtime.displays import enable_dpi_awareness, monitors, place
        from guard_runtime.warning import warning_state
        from guard_runtime.alert_view import WarningView
        shared = self._root is not None
        root = None
        windows = {}
        views = {}
        started = time.monotonic()
        poll_id = None
        failure = []
        deadline = (time.monotonic() + preview_seconds
                    if preview_seconds is not None else None)

        def closing():
            return (self._deactivate_evt.is_set()
                    or (should_close and should_close())
                    or (deadline is not None and time.monotonic() >= deadline))

        def reconcile():
            attached = monitors(root)
            # Cover newly attached displays before removing obsolete windows.
            for display in attached:
                if display not in windows:
                    window = tk.Toplevel(root)
                    windows[display] = window
                    window.withdraw()
                    window.title("Laptop Guard — prueba" if deadline is not None else "System Alert")
                    window.configure(bg="black")
                    if sys.platform == "win32":
                        window.overrideredirect(True)
                    window.attributes("-topmost", True)
                    window.protocol("WM_DELETE_WINDOW", self.deactivate if deadline is not None else lambda: None)
                    if deadline is not None:
                        tk.Button(window, text="PRUEBA — Cerrar (Esc)",
                                  command=self.deactivate).pack(pady=20)
                        window.bind("<Escape>", lambda event: self.deactivate())
                    views[display] = WarningView(
                        window, self._config, display.width, display.height,
                        standard_message=self._config.message == MESSAGE_TEMPLATE.format(phone=self._config.phone))
                    window.deiconify()
                    place(window, display)
                    window.lift()
                    if deadline is not None:
                        window.focus_force()
            for display in tuple(windows):
                if display not in attached:
                    windows.pop(display).destroy()
                    views.pop(display)

        def animate():
            elapsed = time.monotonic() - started
            state = warning_state(elapsed, flash=self._config.flash_warning,
                                  simulation=self._config.show_simulation)
            for view in views.values():
                view.render(elapsed, state)

        last_scan = 0

        def poll():
            nonlocal poll_id, last_scan
            poll_id = None
            try:
                if closing():
                    root.quit()
                    return
                now = time.monotonic()
                if now - last_scan >= 1:
                    reconcile()
                    last_scan = now
                animate()
            except Exception as exc:
                failure.append(exc)
                root.quit()
                return
            poll_id = root.after(100, poll)

        try:
            if closing():
                return
            if not shared:
                enable_dpi_awareness()
            root = self._root if shared else tk.Tk()
            root.withdraw()
            reconcile()
            animate()
            last_scan = time.monotonic()
            _bring_app_forward()
            poll_id = root.after(100, poll)
            root.mainloop()
            if failure:
                raise failure[0]
        finally:
            if root is not None:
                if poll_id is not None:
                    root.after_cancel(poll_id)
                for window in windows.values():
                    window.destroy()
                if not shared:
                    root.destroy()

    def deactivate(self) -> None:
        """Thread-safe: signal the tkinter loop to close."""
        self._deactivate_evt.set()


def _bring_app_forward() -> None:
    """macOS only activates an app when its first window appears; the
    warning screen comes much later, while the intruder's app is in
    front, so ask AppKit to bring the guard forward."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception as exc:
        print(f"  [Guard] could not bring the app forward: {exc}",
              file=sys.stderr)


# ──────────────────────────────────────────────
# 4. POWER MANAGER  (Open/Closed, Dependency Inversion)
# ──────────────────────────────────────────────
class PowerManager(ABC):
    @abstractmethod
    def prevent_shutdown(self) -> None: ...

    @abstractmethod
    def restore(self) -> None: ...


class WindowsPowerManager(PowerManager):
    """Prevent automatic sleep for this thread without changing the power plan.

    Explicit sleep, shutdown and restart remain controlled by Windows.
    """
    def prevent_shutdown(self) -> None:
        import ctypes
        if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
            log_debug("Could not prevent automatic sleep")

    def restore(self) -> None:
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


class NoopPowerManager(PowerManager):
    """For non-Windows or testing - does nothing."""

    def prevent_shutdown(self) -> None: ...
    def restore(self) -> None: ...


def _make_power() -> PowerManager:
    if platform.system().lower() == "windows":
        return WindowsPowerManager()
    return NoopPowerManager()


# ──────────────────────────────────────────────
# 6. INPUT GUARD  (Single Responsibility)
# ──────────────────────────────────────────────
class InputGuard:
    """Watches keyboard + mouse, suppresses input, and fires callbacks."""

    def __init__(
        self,
        config: GuardConfig,
        on_unauthorized: Callable[[], None],
        on_deactivate: Callable[[], None],
        on_attempt: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._on_unauth = on_unauthorized
        self._on_deact = on_deactivate
        self._on_attempt = on_attempt or (lambda source: None)
        self._triggered = threading.Event()   # fire alarm only once per session
        self._active = True
        self._expected = {k.lower() for k in config.key_combo}
        self._pressed: set[str] = set()
        self._event_lock = threading.RLock()
        self._listeners = []
        self._move_count = 0
        self._move_started = None
        self._last_move_log = 0.0
        # why the input watcher gave up, once it has (e.g. "accessibility")
        self.failure: Optional[str] = None

    # ---- internal helpers ------------------------------------------------
    @staticmethod
    def _key_name(key) -> str:
        """Normalize pynput keys: 'ctrl_l'->'ctrl', KeyCode 'z'->'z'."""
        if hasattr(key, "name") and key.name:
            s = key.name.lower()
        elif getattr(key, "char", None) is not None:
            s = key.char.lower()
        else:
            s = str(key).lower().strip("'\"")
        s = s.replace("key.", "")
        # With Ctrl held, Windows reports letters as control codes
        # (Ctrl+Z arrives as '\x1a' instead of 'z') - map them back.
        if len(s) == 1 and ord(s) < 32:
            s = chr(ord(s) + 96)
        for suffix in ("_l", "_r", "_gr"):
            if s.endswith(suffix):
                return s[: -len(suffix)]
        return s

    # ---- event handlers (shared by the in-process and helper paths) ------
    def _handle_press(self, kn: str) -> None:
        with self._event_lock:
            self._press(kn)

    def _press(self, kn: str) -> None:
        if not self._active:
            return
        self._pressed.add(kn)

        if self._expected.issubset(self._pressed):  # correct combo → deactivate
            self._active = False
            self._on_deact()
            return

        if not self._triggered.is_set():            # first intrusion → alarm
            self._triggered.set()
            self._on_unauth()
        # Record activity, never typed characters or the secret combination.
        self._on_attempt("key:press")
        if kn == "f4" and "alt" in self._pressed:
            self._on_attempt("shortcut:alt+f4")

    def _handle_release(self, kn: str) -> None:
        with self._event_lock:
            self._pressed.discard(kn)

    def _handle_mouse(self, kind: str) -> None:
        with self._event_lock:
            self._mouse(kind)

    def _mouse(self, kind: str) -> None:
        if not self._active:
            return
        if not self._triggered.is_set():
            self._triggered.set()
            self._on_unauth()
        if kind == "move":
            self._move_count += 1
            if self._move_started is None:
                from guard_runtime.audit import timestamp
                self._move_started = timestamp()
            if time.monotonic() - self._last_move_log >= 1:
                self._flush_moves()
        else:
            self._on_attempt(f"mouse:{kind}")

    def _flush_moves(self):
        if self._move_count:
            self._on_attempt(f"mouse:move:{self._move_count}:{self._move_started}")
            self._move_count = 0
            self._move_started = None
            self._last_move_log = time.monotonic()

    def stop(self):
        with self._event_lock:
            self._active = False
            self._flush_moves()
        for listener in self._listeners:
            listener.stop()

    # ---- public ----------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def triggered(self) -> threading.Event:
        """Set once the first unauthorized input has been detected."""
        return self._triggered

    def start(self) -> None:
        """Runs in its own thread. Blocks until deactivated."""
        try:
            if sys.platform == "darwin":
                self._start_helper()
            else:
                self._start_pynput()
        except Exception as exc:
            self.failure = str(exc)
            log_debug(f"input watcher failed: {exc}")
        finally:
            was_active = self._active
            self.stop()
            if was_active or self.failure:
                self._on_deact()

    # ---- platform implementations -----------------------------------------
    def _start_helper(self) -> None:
        """macOS: listen via a helper child process (see input_helper_main).

        The helper reports one event per line on its stdout
        ("key:press:ctrl", "key:release:ctrl", "mouse:move", ...). If the
        helper dies, the guard deactivates rather than leaving the user
        with suppressed input and no way to turn it off; the reason it
        gave ("error:fatal:<reason>") is kept in self.failure for the UI.
        """
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, INPUT_HELPER_ARG]
        else:
            cmd = [sys.executable, os.path.abspath(__file__),
                   INPUT_HELPER_ARG]
        log_debug(f"starting input helper: {cmd}")
        # the helper's stderr (pynput warnings, tracebacks) goes to the
        # debug log: a windowed app has nowhere else to show it
        try:
            err = open(DEBUG_LOG, "a", encoding="utf-8")
        except OSError:
            err = None
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=err if err is not None else subprocess.DEVNULL,
            text=True, cwd=app_dir())
        try:
            for line in proc.stdout:
                if not self._active:
                    break
                event = line.strip()
                if event.startswith("key:press:"):
                    self._handle_press(event[len("key:press:"):])
                elif event.startswith("key:release:"):
                    self._handle_release(event[len("key:release:"):])
                elif event.startswith("mouse:"):
                    self._handle_mouse(event[len("mouse:"):])
                elif event.startswith("error:fatal:"):
                    self.failure = event[len("error:fatal:"):] or "helper"
                    log_debug(f"input helper gave up: {self.failure}")
                elif event.startswith("error:"):
                    log_debug(f"input helper: {event[len('error:'):]}")
            if self._active:
                self.failure = self.failure or "helper"
                log_debug("input helper exited while the guard was active; "
                          "guard deactivated")
        finally:
            self._active = False
            try:
                proc.terminate()
                log_debug(f"input helper exit code: {proc.wait(timeout=5)}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                log_debug(f"input helper shutdown: {exc}")
            if err is not None:
                err.close()

    def _start_pynput(self) -> None:
        """Windows/Linux: in-process listeners (no TSM restriction there)."""
        from pynput import keyboard, mouse

        # ── keyboard callbacks (pynput runs them in ITS OWN thread) ──
        def on_press(key):
            self._handle_press(self._key_name(key))

        def on_release(key):
            self._handle_release(self._key_name(key))

        # ── mouse callbacks ──
        def on_move(x, y):
            self._handle_mouse("move")

        def on_click(x, y, button, pressed_flag):
            if pressed_flag:
                self._handle_mouse("click")

        def on_scroll(x, y, dx, dy):
            self._handle_mouse("scroll")

        # suppress=True blocks input from reaching the OS; fall back to
        # passive listeners on platforms where suppression is unsupported
        try:
            k_list = keyboard.Listener(on_press=on_press,
                                       on_release=on_release, suppress=True)
            m_list = mouse.Listener(on_move=on_move,
                                    on_click=on_click, on_scroll=on_scroll, suppress=True)
            self._listeners = [k_list, m_list]
            k_list.start()
            m_list.start()
        except Exception as exc:
            for listener in self._listeners:
                listener.stop()
            self._on_attempt("input:passive_fallback")
            print(f"  [Guard] input suppression unavailable ({exc}); "
                  "falling back to passive listening", file=sys.stderr)
            k_list = keyboard.Listener(on_press=on_press, on_release=on_release)
            m_list = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
            self._listeners = [k_list, m_list]
            k_list.start()
            m_list.start()

        # Keep this thread alive while guard is active
        while self._active:
            if not k_list.is_alive() or not m_list.is_alive():
                raise RuntimeError("Input listener stopped unexpectedly")
            with self._event_lock:
                if time.monotonic() - self._last_move_log >= 1:
                    self._flush_moves()
            time.sleep(0.2)

        k_list.stop()
        m_list.stop()


# ──────────────────────────────────────────────
# 6b. INPUT HELPER PROCESS  (macOS)
# ──────────────────────────────────────────────
INPUT_HELPER_ARG = "--laptop-guard-input-helper"


def input_helper_main() -> None:
    """Run the pynput listeners in a dedicated helper process.

    Entry point for the child process spawned by InputGuard on macOS.
    macOS 26 (Tahoe) kills any process that calls the Text Services
    Manager off the main dispatch queue, and pynput's keyboard listener
    does exactly that when it runs on a background thread (SIGTRAP in
    TSMGetInputSourceProperty; unfixed upstream as of pynput 1.7.7). The
    listener therefore lives in this helper, whose MAIN thread is free to
    host the keyboard listener's run loop. Detected input is reported to
    the parent as one line per event on stdout.

    The helper must never outlive its parent: it watches stdin and exits
    as soon as the pipe closes (i.e. the parent died), so input is never
    left suppressed with nobody able to turn it off.
    """
    # A windowed PyInstaller build may start with sys.stdout set to None;
    # the parent reads events from the stdout pipe, so it must exist.
    if sys.stdout is None:
        sys.stdout = open(os.dup(1), "w", encoding="utf-8", closefd=False)
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    def _emit(event: str) -> None:
        try:
            sys.stdout.write(event + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            os._exit(0)                    # parent gone

    def _watch_parent() -> None:
        try:
            sys.stdin.read()               # EOF == parent process died
        except Exception:
            pass
        os._exit(0)

    threading.Thread(target=_watch_parent, daemon=True).start()

    from pynput import keyboard, mouse

    def on_press(key):
        _emit("key:press:" + InputGuard._key_name(key))

    def on_release(key):
        _emit("key:release:" + InputGuard._key_name(key))

    def on_move(x, y):
        _emit("mouse:move")

    def on_click(x, y, button, is_pressed):
        if is_pressed:
            _emit("mouse:click")

    def on_scroll(x, y, dx, dy):
        _emit("mouse:scroll")

    def _launch(suppress: bool) -> str:
        """Run the listeners until the keyboard listener returns.

        Nothing here ever calls stop(), so run() returning at all means
        macOS refused the event tap: pynput reports that only by
        returning early, never by raising. The result names the likely
        cause for the parent.
        """
        m_list = mouse.Listener(on_move=on_move, on_click=on_click,
                                on_scroll=on_scroll, suppress=suppress)
        k_list = keyboard.Listener(on_press=on_press,
                                   on_release=on_release, suppress=suppress)
        m_list.start()
        try:
            # Blocks; MUST run on this process's main thread so pynput's
            # Text Services Manager calls stay on the main dispatch queue.
            k_list.run()
        finally:
            m_list.stop()
        trusted = getattr(k_list, "IS_TRUSTED", False)
        return "tap" if trusted else "accessibility"

    # suppress=True blocks input from reaching the OS. Without the
    # Accessibility grant no tap can be created at all, so give up and
    # let the parent explain; if the grant is there but the blocking tap
    # still fails, at least keep watching passively.
    try:
        reason = _launch(suppress=True)
        if reason == "accessibility":
            _emit("error:fatal:accessibility")
            return
        _emit("error:input suppression unavailable; watching only")
        _emit("error:fatal:" + _launch(suppress=False))
    except Exception as exc:
        _emit("error:fatal:" + str(exc).replace("\n", " "))


# ──────────────────────────────────────────────
# 7. ORCHESTRATOR  (Dependency Inversion - uses abstractions)
# ──────────────────────────────────────────────
class LaptopGuard:
    """Single entry-point that wires everything together."""

    def __init__(self, config: Optional[GuardConfig] = None,
                 root: Optional[tk.Tk] = None, *, paths=None,
                 alarm=None, screen=None, power=None, recorder=None,
                 audit=None, system_events=None) -> None:
        self.config = config or GuardConfig()
        self.paths = paths or RuntimePaths()
        self._audit = audit or AuditLog(self.paths)
        self._alarm: AlarmPlayer = alarm or _make_alarm(self.config.alarm_style)
        self._screen = screen or FakeScreen(self.config, root)
        self._power: PowerManager = power or _make_power()
        self._recorder = recorder or WebcamRecorder(self.config, self.paths, self._audit)
        self._system = system_events or SystemEvents(self.paths, self._audit)
        self._media_threads = []
        self._input = None
        self._unlocked = False

    # ---- callbacks (called from InputGuard / pynput threads) -------------
    def _on_unauthorized(self) -> None:
        # NEVER block the pynput listener thread here. A low-level input
        # hook (Windows) or CGEventTap (macOS) must return immediately -
        # stalling it makes the OS drop events or kill the hook/tap,
        # which is what killed the combo detection.
        # Note: the warning screen is intentionally NOT started here;
        # activate() runs it on the MAIN thread (Tk/Cocoa requirement).
        self._audit.emit("alarm_triggered")
        alarm_thread = threading.Thread(
            target=self._alarm.play,
            args=(self.config.alarm_duration_sec,),
            name="guard-alarm",
            daemon=True,
        )
        video_thread = threading.Thread(target=self._recorder.record,
                                        name="guard-video", daemon=True)
        self._media_threads = [alarm_thread, video_thread]
        alarm_thread.start()
        video_thread.start()

    def _on_deactivate(self) -> None:
        if self._input and self._input.failure:
            self._audit.emit("input_watcher_failed", error=self._input.failure)
        else:
            self._unlocked = True
            self._audit.emit("guard_unlocked", method="key_combination")
        self._screen.deactivate()    # thread-safe → closes tkinter window
        self._alarm.stop()

    def _log_attempt(self, source: str) -> None:
        if source.startswith("mouse:move:"):
            _, _, count, started = source.split(":", 3)
            self._audit.emit("input_attempt", source="mouse:move", count=int(count),
                             first_observed_at=started)
        else:
            self._audit.emit("input_attempt", source=source, count=1)

    # ---- public API ------------------------------------------------------
    def activate(self, activation_reason="manual", can_activate=None) -> Optional[str]:
        """Block until the guard is deactivated.

        Returns None after a normal deactivation, or a short reason
        ("accessibility", "helper", ...) when the input watcher failed
        and the guard switched itself off.
        """
        # Do NOT print the combo here: the console stays visible until the
        # first trigger, and an "intruder" could just read the way out.
        print("\n  [Guard] ACTIVE - keyboard and mouse are blocked.\n")

        guard = InputGuard(
            config=self.config,
            on_unauthorized=self._on_unauthorized,
            on_deactivate=self._on_deactivate,
            on_attempt=self._log_attempt,
        )
        self._input = guard
        worker = threading.Thread(target=guard.start, daemon=True)
        self.paths.ensure()
        instance = InstanceLock(self.paths.logs / "guard.lock")
        instance.acquire()
        reason = "error"

        # Main thread: wait for the first intrusion, then run the warning
        # screen HERE. Tk on macOS (Cocoa) only works on the main thread,
        # and it is equally happy there on Windows - so show() must not
        # run on a listener or daemon thread.
        try:
            self._audit.start()
            self._system.start()
            if can_activate is not None and not can_activate():
                reason = "activation_cancelled"
                self._audit.emit("activation_cancelled", reason="activity_or_pause")
                return None
            self._power.prevent_shutdown()
            self._audit.emit("guard_activated", reason=activation_reason)
            self._audit.flush()
            worker.start()
            while guard.is_active and not guard.triggered.is_set():
                if self._audit.error:
                    raise OSError(str(self._audit.error))
                time.sleep(0.2)
            if guard.is_active:
                self._screen.show(should_close=lambda: not guard.is_active or bool(self._audit.error))
            if self._audit.error:
                raise OSError(str(self._audit.error))
            reason = "input_failure" if guard.failure else ("key_combination" if self._unlocked else "screen_closed")
        except KeyboardInterrupt:
            reason = "keyboard_interrupt"
        finally:
            guard.stop()
            self._screen.deactivate()
            if worker.ident:
                worker.join(timeout=6)
            self._alarm.stop()
            for thread in self._media_threads:
                timeout = max(self.config.record_seconds, 0) + 5 if thread.name == "guard-video" else 2
                thread.join(timeout=timeout)
                if thread.is_alive():
                    self._audit.emit("media_stop_timeout", thread=thread.name)
            self._recorder.stop()
            self._alarm.stop()
            self._power.restore()
            self._system.stop()
            try:
                self._audit.close(reason)
            finally:
                instance.release()
        if guard.failure:
            print(f"  [Guard] DEACTIVATED - input watcher failed "
                  f"({guard.failure}); see {DEBUG_LOG}\n", file=sys.stderr)
        else:
            print("  [Guard] DEACTIVATED - all normal.\n")
        return guard.failure


# ──────────────────────────────────────────────
# 8. ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # Settings come from guard_config.json next to this script (or next to
    # the executable in a frozen build) - edit them with the setup window
    # (guard_setup.py / setup.bat / Setup.command).
    # Built-in defaults apply when the file does not exist yet.
    os.chdir(app_dir())
    if INPUT_HELPER_ARG in sys.argv[1:]:
        # spawned by InputGuard on macOS: just run the input listeners
        input_helper_main()
    elif LaptopGuard(load_config()).activate():
        sys.exit(1)
