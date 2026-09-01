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


# ──────────────────────────────────────────────
# 1. CONFIGURATION  (Single Responsibility)
# ──────────────────────────────────────────────
def app_dir() -> str:
    """Folder that holds the app's data files (config, log, webcam clip).

    In a frozen (PyInstaller) build, __file__ points inside a temporary
    extraction folder that is deleted on exit, so the executable's own
    folder is used instead - settings survive across runs there.

    Exception: on frozen macOS the executable lives inside the .app
    bundle, and an unsigned app downloaded from the internet runs from a
    read-only translocated path, so data files go to the standard
    per-user Application Support folder instead.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            path = os.path.expanduser(
                "~/Library/Application Support/LaptopGuard")
            os.makedirs(path, exist_ok=True)
            return path
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(app_dir(), "guard_config.json")

MESSAGE_TEMPLATE = (
    "⚠️  SYSTEM BREACH DETECTED  ⚠️\n\n"
    "ALL FILES WILL BE PERMANENTLY DELETED IN 2 HOURS.\n\n"
    "Call {phone} to avoid data loss.\n"
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
    log_file: str = "guard.log"        # intrusion attempt log
    record_seconds: int = 5            # webcam clip length; 0 disables recording
    clip_file: str = "intruder.mp4"    # webcam clip output

    def __post_init__(self) -> None:
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
    """Loud square-wave alarm via pygame + numpy."""

    def __init__(self) -> None:
        # hide pygame's "Hello from the pygame community" banner so the
        # console stays clean (must be set before the pygame import)
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame  # noqa - deferred so import errors surface at use-time
        self._pygame = pygame
        self._sound = None     # MUST keep a reference (see play())
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

    def play(self, duration_sec: int) -> None:
        try:
            import numpy as np
            sr = 44_100
            freq = 800  # Hz - harsh alarm tone
            t = np.linspace(0, 1.0, sr, dtype=np.float32)
            tone = (np.sign(np.sin(2 * np.pi * freq * t)) * 16_000).astype(np.int16)
            # stereo frames, matching the mixer's channels=2 format
            wave = np.column_stack((tone, tone))
            # Keep the Sound in self._sound: pygame stops playback as soon
            # as the Sound object is garbage-collected, which is exactly
            # what made the alarm "sound once and stop" before.
            self._sound = self._pygame.mixer.Sound(buffer=wave.tobytes())
            # loops counts REPEATS after the first play, hence the -1
            self._sound.play(loops=max(0, duration_sec - 1))  # 1 s per loop
        except Exception as exc:
            # never leave the guard silent: degrade to the winsound beeper
            print(f"  [Guard] pygame alarm failed: {exc}", file=sys.stderr)
            try:
                WinsoundAlarm().play(duration_sec)
            except Exception as exc2:
                print(f"  [Guard] winsound fallback failed: {exc2}",
                      file=sys.stderr)

    def stop(self) -> None:
        try:
            if self._sound is not None:
                self._sound.stop()
                self._sound = None
            self._pygame.mixer.stop()
        except Exception as exc:
            print(f"  [Guard] alarm stop failed: {exc}", file=sys.stderr)


class WinsoundAlarm(AlarmPlayer):
    """Pure-stdlib fallback (Windows only)."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def play(self, duration_sec: int) -> None:
        import winsound
        self._stop.clear()
        end = time.time() + duration_sec
        while time.time() < end and not self._stop.is_set():
            winsound.Beep(800, 150)
            winsound.Beep(1200, 150)

    def stop(self) -> None:
        self._stop.set()


class _SilentAlarm(AlarmPlayer):
    """Last-resort fallback when neither pygame nor winsound is available."""

    def play(self, duration_sec: int) -> None: ...
    def stop(self) -> None: ...


def _make_alarm() -> AlarmPlayer:
    """Factory - Dependency Inversion: caller gets an abstraction."""
    try:
        return PygameAlarm()
    except Exception as exc:
        if platform.system().lower() != "windows":
            # winsound does not exist outside Windows; without pygame
            # there is no alarm, but the rest of the guard keeps working
            print(f"  [Guard] pygame unavailable ({exc}); alarm disabled",
                  file=sys.stderr)
            return _SilentAlarm()
        print(f"  [Guard] pygame unavailable ({exc}); using winsound fallback",
              file=sys.stderr)
        return WinsoundAlarm()


# ──────────────────────────────────────────────
# 3. FAKE SCREEN  (Single Responsibility)
# ──────────────────────────────────────────────
class FakeScreen:
    """Full-screen black tkinter window with the warning text."""

    def __init__(self, config: GuardConfig) -> None:
        self._config = config
        self._deactivate_evt = threading.Event()   # thread-safe signal

    def show(self) -> None:
        """Runs the tkinter mainloop; blocks until deactivate() is called.

        MUST be called on the main thread - Tk on macOS (Cocoa) rejects
        windows created on background threads.
        """
        self._deactivate_evt.clear()

        try:
            root = tk.Tk()
            root.title("System Alert")
            root.attributes("-fullscreen", True)
            root.configure(bg="black")
            root.attributes("-topmost", True)

            tk.Label(
                root, text=self._config.message,
                fg="red", bg="black",
                font=("Arial", 22, "bold"),
                wraplength=900, justify="center",
            ).pack(expand=True)

            root.protocol("WM_DELETE_WINDOW", lambda: None)  # block × button

            def _poll() -> None:
                if self._deactivate_evt.is_set():
                    root.destroy()
                    return
                root.after(100, _poll)          # check every 100 ms

            root.after(100, _poll)
            root.mainloop()                     # ← blocks here
        except Exception as exc:
            # a screen failure must never abort activate()'s main thread
            print(f"  [Guard] warning screen failed: {exc}", file=sys.stderr)

    def deactivate(self) -> None:
        """Thread-safe: signal the tkinter loop to close."""
        self._deactivate_evt.set()


# ──────────────────────────────────────────────
# 4. POWER MANAGER  (Open/Closed, Dependency Inversion)
# ──────────────────────────────────────────────
class PowerManager(ABC):
    @abstractmethod
    def prevent_shutdown(self) -> None: ...

    @abstractmethod
    def restore(self) -> None: ...


class WindowsPowerManager(PowerManager):
    """Prevents sleep / hibernate via powercfg (Windows).

    The previous standby timeouts are captured on prevent and put back on
    restore, so the user's power plan is left exactly as it was found.
    """

    _SUB_SLEEP   = "238c9fa8-0aad-41ed-83f4-97be242c8dc2"  # Sleep subgroup
    _STANDBYIDLE = "29f6c1db-86da-48dc-9fcb-f6d1e0da6a9f"  # "Sleep after" setting

    def __init__(self) -> None:
        import re
        import subprocess
        self._re = re
        self._sp = subprocess
        self._saved: Optional[tuple[int, int]] = None   # (ac, dc) seconds

    # ---- helpers ---------------------------------------------------------
    def _run(self, args: list[str]) -> str:
        try:
            res = self._sp.run(["powercfg", *args],
                               capture_output=True, text=True, check=False)
            return res.stdout or ""
        except OSError as exc:
            print(f"  [Guard] powercfg failed: {exc}", file=sys.stderr)
            return ""

    def _current_timeouts(self) -> Optional[tuple[int, int]]:
        out = self._run(["/query", "SCHEME_CURRENT",
                         self._SUB_SLEEP, self._STANDBYIDLE])
        pairs = self._re.findall(
            r"Current (AC|DC) Power Setting Index:\s*0x([0-9a-fA-F]+)", out)
        vals = {src.lower(): int(hexv, 16) for src, hexv in pairs}
        if "ac" in vals and "dc" in vals:
            return vals["ac"], vals["dc"]
        return None

    # ---- interface -------------------------------------------------------
    def prevent_shutdown(self) -> None:
        self._saved = self._current_timeouts()
        for source in ("ac", "dc"):
            # value index for STANDBYIDLE is in seconds; 0 = never
            self._run([f"/set{source}valueindex", "SCHEME_CURRENT",
                       self._SUB_SLEEP, self._STANDBYIDLE, "0"])

    def restore(self) -> None:
        if self._saved is None:
            return
        ac, dc = self._saved
        self._run(["/setacvalueindex", "SCHEME_CURRENT",
                   self._SUB_SLEEP, self._STANDBYIDLE, str(ac)])
        self._run(["/setdcvalueindex", "SCHEME_CURRENT",
                   self._SUB_SLEEP, self._STANDBYIDLE, str(dc)])
        self._saved = None


class NoopPowerManager(PowerManager):
    """For non-Windows or testing - does nothing."""

    def prevent_shutdown(self) -> None: ...
    def restore(self) -> None: ...


def _make_power() -> PowerManager:
    if platform.system().lower() == "windows":
        return WindowsPowerManager()
    return NoopPowerManager()


# ──────────────────────────────────────────────
# 5. WEBCAM RECORDER  (Single Responsibility)
# ──────────────────────────────────────────────
class WebcamRecorder:
    """Records a short webcam clip when the alarm triggers.

    Requires opencv-python; degrades gracefully (warning on stderr) when the
    package or a camera is not available. Designed to run on a daemon thread.
    """

    def __init__(self, config: GuardConfig) -> None:
        self._config = config

    def record(self) -> None:
        secs = self._config.record_seconds
        if secs <= 0:
            return
        try:
            import cv2
        except ImportError:
            print("  [Guard] opencv-python not installed; skipping webcam clip",
                  file=sys.stderr)
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("  [Guard] no webcam available; skipping clip", file=sys.stderr)
            cap.release()
            return

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

            writer = self._open_writer(cv2, self._config.clip_file,
                                       fps, width, height)
            if writer is None:
                return

            deadline = time.time() + secs
            while time.time() < deadline:
                ok, frame = cap.read()
                if ok:
                    writer.write(frame)
                else:
                    time.sleep(0.01)
            writer.release()
            print(f"  [Guard] webcam clip saved to {self._config.clip_file}")
        except Exception as exc:
            print(f"  [Guard] webcam recording failed: {exc}", file=sys.stderr)
        finally:
            cap.release()

    @staticmethod
    def _open_writer(cv2, path: str, fps: float,
                     width: int, height: int):
        """Try mp4v first, fall back to XVID/avi if the codec is missing."""
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        if writer.isOpened():
            return writer
        writer.release()
        alt = path.rsplit(".", 1)[0] + ".avi"
        writer = cv2.VideoWriter(alt, cv2.VideoWriter_fourcc(*"XVID"),
                                 fps, (width, height))
        if writer.isOpened():
            return writer
        writer.release()
        print("  [Guard] could not open a video writer", file=sys.stderr)
        return None


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

    # ---- internal helpers ------------------------------------------------
    @staticmethod
    def _key_name(key) -> str:
        """Normalize pynput keys: 'ctrl_l'->'ctrl', KeyCode 'z'->'z'."""
        if hasattr(key, "name") and key.name:
            s = key.name.lower()
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
        self._on_attempt(f"key:{kn}")

    def _handle_release(self, kn: str) -> None:
        self._pressed.discard(kn)

    def _handle_mouse(self, kind: str) -> None:
        if not self._active:
            return
        if not self._triggered.is_set():
            self._triggered.set()
            self._on_unauth()
            self._on_attempt(f"mouse:{kind}")
        elif kind == "click":
            # clicks are logged even after the trigger; moves are not,
            # so a moving mouse cannot flood the log file
            self._on_attempt("mouse:click")

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
        if sys.platform == "darwin":
            self._start_helper()
        else:
            self._start_pynput()

    # ---- platform implementations -----------------------------------------
    def _start_helper(self) -> None:
        """macOS: listen via a helper child process (see input_helper_main).

        The helper reports one event per line on its stdout
        ("key:press:ctrl", "key:release:ctrl", "mouse:move", ...). If the
        helper dies, the guard deactivates rather than leaving the user
        with suppressed input and no way to turn it off.
        """
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, INPUT_HELPER_ARG]
        else:
            cmd = [sys.executable, os.path.abspath(__file__),
                   INPUT_HELPER_ARG]
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, cwd=app_dir())
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
                elif event.startswith("error:"):
                    print(f"  [Guard] input helper: {event[len('error:'):]}",
                          file=sys.stderr)
            if self._active:
                print("  [Guard] input helper exited unexpectedly; "
                      "guard deactivated", file=sys.stderr)
        finally:
            self._active = False
            try:
                proc.terminate()
            except OSError:
                pass

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

        # suppress=True blocks input from reaching the OS; fall back to
        # passive listeners on platforms where suppression is unsupported
        try:
            k_list = keyboard.Listener(on_press=on_press,
                                       on_release=on_release, suppress=True)
            m_list = mouse.Listener(on_move=on_move,
                                    on_click=on_click, suppress=True)
            k_list.start()
            m_list.start()
        except Exception as exc:
            print(f"  [Guard] input suppression unavailable ({exc}); "
                  "falling back to passive listening", file=sys.stderr)
            k_list = keyboard.Listener(on_press=on_press, on_release=on_release)
            m_list = mouse.Listener(on_move=on_move, on_click=on_click)
            k_list.start()
            m_list.start()

        # Keep this thread alive while guard is active
        while self._active:
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

    def _launch(suppress: bool) -> None:
        m_list = mouse.Listener(on_move=on_move, on_click=on_click,
                                suppress=suppress)
        k_list = keyboard.Listener(on_press=on_press,
                                   on_release=on_release, suppress=suppress)
        m_list.start()
        try:
            # Blocks; MUST run on this process's main thread so pynput's
            # Text Services Manager calls stay on the main dispatch queue.
            k_list.run()
        finally:
            m_list.stop()

    # suppress=True blocks input from reaching the OS; if the tap cannot
    # be created (e.g. the Accessibility grant is missing), fall back to
    # passive listeners that only watch
    try:
        _launch(suppress=True)
    except Exception as exc:
        _emit("error:" + str(exc).replace("\n", " "))
        try:
            _launch(suppress=False)
        except Exception as exc2:
            _emit("error:fatal: " + str(exc2).replace("\n", " "))


# ──────────────────────────────────────────────
# 7. ORCHESTRATOR  (Dependency Inversion - uses abstractions)
# ──────────────────────────────────────────────
class LaptopGuard:
    """Single entry-point that wires everything together."""

    def __init__(self, config: Optional[GuardConfig] = None) -> None:
        self.config = config or GuardConfig()
        self._alarm: AlarmPlayer = _make_alarm()
        self._screen = FakeScreen(self.config)
        self._power: PowerManager = _make_power()
        self._recorder = WebcamRecorder(self.config)

    # ---- callbacks (called from InputGuard / pynput threads) -------------
    def _on_unauthorized(self) -> None:
        # NEVER block the pynput listener thread here. A low-level input
        # hook (Windows) or CGEventTap (macOS) must return immediately -
        # stalling it makes the OS drop events or kill the hook/tap,
        # which is what killed the combo detection.
        # Note: the warning screen is intentionally NOT started here;
        # activate() runs it on the MAIN thread (Tk/Cocoa requirement).
        threading.Thread(
            target=self._alarm.play,
            args=(self.config.alarm_duration_sec,),
            daemon=True,
        ).start()
        threading.Thread(target=self._recorder.record, daemon=True).start()

    def _on_deactivate(self) -> None:
        self._screen.deactivate()    # thread-safe → closes tkinter window
        self._alarm.stop()

    def _log_attempt(self, source: str) -> None:
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.config.log_file, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp}  unauthorized input: {source}\n")
        except OSError as exc:
            print(f"  [Guard] log write failed: {exc}", file=sys.stderr)

    # ---- public API ------------------------------------------------------
    def activate(self) -> None:
        # Do NOT print the combo here: the console stays visible until the
        # first trigger, and an "intruder" could just read the way out.
        print("\n  [Guard] ACTIVE - keyboard and mouse are blocked.\n")

        self._power.prevent_shutdown()

        guard = InputGuard(
            config=self.config,
            on_unauthorized=self._on_unauthorized,
            on_deactivate=self._on_deactivate,
            on_attempt=self._log_attempt,
        )
        worker = threading.Thread(target=guard.start, daemon=True)
        worker.start()

        # Main thread: wait for the first intrusion, then run the warning
        # screen HERE. Tk on macOS (Cocoa) only works on the main thread,
        # and it is equally happy there on Windows - so show() must not
        # run on a listener or daemon thread.
        try:
            while guard.is_active and not guard.triggered.is_set():
                time.sleep(0.2)
            if guard.is_active:
                self._screen.show()     # blocks until _on_deactivate()
        except KeyboardInterrupt:
            pass

        self._alarm.stop()
        self._power.restore()
        print("  [Guard] DEACTIVATED - all normal.\n")


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
    else:
        LaptopGuard(load_config()).activate()
