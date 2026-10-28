"""Per-user idle watcher, cancellable warning and pause/resume controls."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime

from .idle import IdlePolicy, WindowsIdle
from .storage import InstanceLock, RuntimePaths, atomic_json, read_json

IDLE_SECONDS = 15 * 60


def settings(paths):
    value = read_json(paths.root / "auto_guard.json")
    return {"enabled": value.get("enabled", False) is True, "idle_seconds": IDLE_SECONDS}


def set_enabled(paths, enabled):
    atomic_json(paths.root / "auto_guard.json", {"enabled": bool(enabled), "idle_seconds": IDLE_SECONDS})


def command(mode):
    if getattr(sys, "frozen", False):
        return [sys.executable, mode]
    from pathlib import Path
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "guard_app.py"), mode]


def launch(mode):
    return subprocess.Popen(command(mode), env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def guard_busy(paths):
    lock = InstanceLock(paths.logs / "guard.lock")
    try:
        lock.acquire()
    except RuntimeError:
        return True
    else:
        lock.release()
        return False


def eligible(paths, detector):
    return settings(paths)["enabled"] and detector.desktop_available() and detector.seconds() >= IDLE_SECONDS


class AutoWatcher:
    def __init__(self, root, paths=None, detector=None):
        self.root = root
        self.paths = paths or RuntimePaths()
        self.paths.ensure()
        self.detector = detector or WindowsIdle()
        self.policy = IdlePolicy()
        self.child = None
        self.warning_visible = False
        self.last_state = None
        self.last_status = 0
        self.root.withdraw()
        self.root.title("Laptop Guard — activación automática")
        self.root.resizable(False, False)
        self.label = tk.Label(root, padx=25, pady=20, font=("Arial", 12))
        self.label.pack()
        tk.Button(root, text="Cancelar y esperar otros 15 minutos", command=self.cancel).pack(padx=20, pady=(0, 15))
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        self.root.bind("<Escape>", lambda event: self.cancel())

    def event(self, event, **details):
        # Separate append-only file: the active guard owns guard.jsonl/session.json.
        with (self.paths.logs / "auto_guard.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": datetime.now().astimezone().isoformat(),
                                     "event": event, **details}, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def cancel(self):
        self.policy.reset(time.monotonic())
        self.hide_warning()
        self.event("idle_countdown_cancelled")

    def hide_warning(self):
        self.root.withdraw()
        self.warning_visible = False

    def tick(self):
        now = time.monotonic()
        try:
            enabled = settings(self.paths)["enabled"]
            if self.child and self.child.poll() is not None:
                self.event("idle_guard_exited", exit_code=self.child.returncode)
                self.child = None
                self.policy.reset(now)
            busy = self.child is not None or guard_busy(self.paths)
            state, remaining = self.policy.step(now, self.detector.seconds(), enabled=enabled,
                                                available=self.detector.desktop_available(), busy=busy)
            if state == "warning":
                self.label.config(text=f"Laptop Guard se activará en {math.ceil(remaining)} segundos.\n\n"
                                       "Mueve el mouse o pulsa una tecla para cancelar.")
                if not self.warning_visible:
                    self.root.deiconify()
                    self.root.attributes("-topmost", True)
                    self.warning_visible = True
                    self.event("idle_countdown_started", idle_minutes=15)
            else:
                if self.warning_visible and state != "activate":
                    self.event("idle_countdown_cancelled", reason="activity_or_pause")
                self.hide_warning()
            if state == "activate" and eligible(self.paths, self.detector):
                self.event("idle_activation_requested", idle_minutes=15)
                self.child = launch("--activate-idle")
            status = "guard_active" if busy else ("paused" if not enabled else state)
            if status != self.last_state or now - self.last_status >= 10:
                if status != self.last_state:
                    self.event("idle_monitor_state", state=status)
                atomic_json(self.paths.logs / "auto_status.json",
                            {"pid": os.getpid(), "state": status,
                             "updated_at": time.time(), "idle_minutes": 15})
                self.last_state, self.last_status = status, now
        except Exception as exc:
            self.policy.reset(now)
            self.hide_warning()
            from laptop_guard import log_debug
            log_debug(f"idle monitor error (activation skipped): {exc}")
        self.root.after(1000, self.tick)

    def run(self):
        lock = InstanceLock(self.paths.logs / "auto_guard.lock")
        try:
            lock.acquire()
        except RuntimeError:
            self.root.destroy()
            return
        try:
            self.event("idle_monitor_started", idle_minutes=15)
            self.tick()
            self.root.mainloop()
        finally:
            lock.release()


def controls(root):
    paths = RuntimePaths()
    paths.ensure()
    root.title("Laptop Guard — automático 15 minutos")
    root.resizable(False, False)
    label = tk.Label(root, padx=25, pady=20, justify="left", font=("Arial", 11))
    label.pack()
    def enable(value):
        set_enabled(paths, value)
        if value:
            launch("--watch")
        refresh()
    tk.Button(root, text="Activar automático (15 minutos)", command=lambda: enable(True)).pack(padx=20, pady=5, fill="x")
    tk.Button(root, text="Pausar automático", command=lambda: enable(False)).pack(padx=20, pady=5, fill="x")
    tk.Button(root, text="Probar sin bloquear", command=lambda: launch("--test")).pack(padx=20, pady=5, fill="x")
    tk.Button(root, text="Cerrar ventana", command=root.destroy).pack(padx=20, pady=(5, 15), fill="x")
    def refresh():
        enabled = settings(paths)["enabled"]
        status = read_json(paths.logs / "auto_status.json")
        recent = time.time() - status.get("updated_at", 0) < 20
        state = "ACTIVADO" if enabled and recent else ("INICIANDO" if enabled else "PAUSADO")
        label.config(text=f"Automático: {state}\n\n"
                          "Tras 15 minutos sin teclado ni mouse aparece\n"
                          "un aviso de 10 segundos antes de proteger el equipo.\n"
                          "Cerrar esta ventana mantiene tu selección.\n"
                          "Pausar no desactiva una protección ya iniciada.")
    def poll():
        refresh()
        root.after(1000, poll)
    poll()
    root.mainloop()
