"""
guard_setup.py - settings window for laptop-guard.

A small tkinter front end so non-technical users can set the phone number
shown on the warning screen and the secret deactivation combo, without
editing any code. Values are stored in guard_config.json next to this
script. They are shown ONLY here - the guard itself never prints them,
so opening this window is also the way to recover a forgotten combo.

The SettingsForm frame is reused by guard_app.py (the single-icon
launcher); running this file directly opens the standalone window.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from laptop_guard import (
    GuardConfig,
    load_config,
    normalize_combo,
    save_config,
)


class SettingsForm(tk.Frame):
    """The settings form: phone, combo, alarm length, clip length.

    on_saved (optional) is called after a successful save instead of
    showing a messagebox - used by guard_app.py to continue its flow.
    """

    def __init__(self, parent: tk.Misc,
                 on_saved: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self._on_saved = on_saved
        pad = {"padx": 10, "pady": 5}

        tk.Label(self, text="Phone number shown on the warning screen:"
                 ).grid(row=0, column=0, sticky="w", **pad)
        self._phone = tk.Entry(self, width=26)
        self._phone.grid(row=0, column=1, **pad)

        tk.Label(self, text="Secret combo (example: ctrl+shift+z):"
                 ).grid(row=1, column=0, sticky="w", **pad)
        self._combo = tk.Entry(self, width=26)
        self._combo.grid(row=1, column=1, **pad)

        tk.Label(self, text="Alarm length (seconds):"
                 ).grid(row=2, column=0, sticky="w", **pad)
        self._alarm = tk.Spinbox(self, from_=5, to=3600, width=8)
        self._alarm.grid(row=2, column=1, sticky="w", **pad)

        tk.Label(self, text="Webcam clip length (seconds, 0 = off):"
                 ).grid(row=3, column=0, sticky="w", **pad)
        self._record = tk.Spinbox(self, from_=0, to=60, width=8)
        self._record.grid(row=3, column=1, sticky="w", **pad)

        btns = tk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, pady=8)
        tk.Button(btns, text="Save", width=12, default="active",
                  command=self._save).pack(side="left", padx=6)
        tk.Button(btns, text="Restore defaults", width=14,
                  command=lambda: self._fill(GuardConfig())
                  ).pack(side="left", padx=6)

        self._fill(load_config())

    def _fill(self, cfg: GuardConfig) -> None:
        """Reset every field to the given config's values."""
        for entry, value in (
            (self._phone, cfg.phone),
            (self._combo, "+".join(cfg.key_combo)),
            (self._alarm, str(cfg.alarm_duration_sec)),
            (self._record, str(cfg.record_seconds)),
        ):
            entry.delete(0, "end")
            entry.insert(0, value)

    def _save(self) -> None:
        phone = self._phone.get().strip()
        if not phone:
            messagebox.showerror("Missing phone",
                                 "Please type a phone number.")
            return
        try:
            combo = normalize_combo(self._combo.get())
        except ValueError as exc:
            messagebox.showerror("Invalid combo", str(exc))
            return
        try:
            alarm = int(self._alarm.get())
            record = int(self._record.get())
            if alarm <= 0 or record < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid numbers",
                "Alarm length must be above 0; clip length 0 or more.")
            return

        save_config({
            "phone": phone,
            "key_combo": list(combo),
            "alarm_duration_sec": alarm,
            "record_seconds": record,
        })
        if self._on_saved is not None:
            self._on_saved()
        else:
            messagebox.showinfo(
                "Saved",
                "Settings saved.\n"
                "They apply the next time the guard starts.")


class SetupWindow:
    """Standalone settings window (setup.bat / Setup.command)."""

    def __init__(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("Laptop Guard - Settings")
        root.resizable(False, False)

        SettingsForm(root).pack(padx=4, pady=4)
        tk.Label(
            root,
            text="Settings are stored in guard_config.json next to this\n"
                 "script and apply the next time the guard starts. The\n"
                 "guard never shows them on screen while it is running.",
            justify="center", fg="#555",
        ).pack(pady=(0, 10))

    def run(self) -> None:
        self._root.mainloop()


if __name__ == "__main__":
    SetupWindow().run()
