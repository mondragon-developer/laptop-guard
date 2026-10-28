"""Explicit runtime paths and crash-safe small state files."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return str(Path.home() / "Library/Application Support/LaptopGuard")
        executable_dir = Path(sys.executable).resolve().parent
        return str(executable_dir)
    return str(Path(__file__).resolve().parent.parent)


class RuntimePaths:
    def __init__(self, root=None):
        self.root = Path(root or app_dir()).resolve()
        # Local executable and source share evidence, but keep their own settings.
        if root is None and self.root.name == "dist" and (self.root.parent / "guard_app.py").is_file():
            self.root = self.root.parent
        self.logs = self.root / "logs"
        self.videos = self.root / "videos"

    def ensure(self):
        self.logs.mkdir(parents=True, exist_ok=True)
        self.videos.mkdir(parents=True, exist_ok=True)


def atomic_json(path: Path, data: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class InstanceLock:
    """An OS-owned lock; automatically released if the guard crashes."""
    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def acquire(self):
        stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0, 2)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise RuntimeError("Laptop Guard is already running for this data folder.")
        self.stream = stream

    def release(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
