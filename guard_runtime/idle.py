"""Windows idle detection and a small testable activation policy."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


class WindowsIdle:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        self.user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.user32.OpenInputDesktop.restype = wintypes.HANDLE
        self.user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                        ctypes.c_void_p, wintypes.DWORD,
                                                        ctypes.POINTER(wintypes.DWORD)]

    def seconds(self):
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not self.user32.GetLastInputInfo(ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ((self.kernel32.GetTickCount64() - info.dwTime) & 0xFFFFFFFF) / 1000

    def desktop_available(self):
        handle = self.user32.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
        if not handle:
            return False
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            ok = self.user32.GetUserObjectInformationW(handle, 2, name,
                                                       ctypes.sizeof(name), ctypes.byref(needed))
            return bool(ok) and name.value.lower() == "default"
        finally:
            self.user32.CloseDesktop(handle)


class IdlePolicy:
    """Require a fresh idle interval after start, unlock, pause or resume."""
    def __init__(self, now=None, idle_seconds=900, warning_seconds=10):
        self.idle_seconds = idle_seconds
        self.warning_seconds = warning_seconds
        self.reset(time.monotonic() if now is None else now)

    def reset(self, now):
        self.since = now
        self.last_poll = now
        self.warning_at = None

    def step(self, now, input_idle, *, enabled=True, available=True, busy=False):
        if not enabled or not available or busy or now - self.last_poll > 10 or now < self.last_poll:
            self.reset(now)
            return "waiting", 0
        self.last_poll = now
        effective_idle = min(max(0, input_idle), max(0, now - self.since))
        if effective_idle < self.idle_seconds:
            self.warning_at = None
            return "waiting", max(0, self.idle_seconds - effective_idle)
        if self.warning_at is None:
            self.warning_at = now
        remaining = self.warning_seconds - (now - self.warning_at)
        if remaining > 0:
            return "warning", remaining
        self.reset(now)
        return "activate", 0
