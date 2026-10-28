"""Append-only audit trail; input callbacks enqueue without disk I/O."""
from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from datetime import datetime

from .storage import RuntimePaths, atomic_json, read_json


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class AuditLog:
    def __init__(self, paths: RuntimePaths):
        self.paths = paths
        self.session = uuid.uuid4().hex
        self.state_path = paths.logs / "session.json"
        self.queue = queue.Queue()
        self.error = None
        self.worker = None
        self._enqueue_lock = threading.Lock()
        self._accepting = True

    def start(self):
        self.paths.ensure()
        self.stream = (self.paths.logs / "guard.jsonl").open("a", encoding="utf-8")
        # A newline also isolates a potentially torn final record after power loss.
        self.stream.write("\n")
        self.stream.flush()
        self.worker = threading.Thread(target=self._write, name="guard-audit", daemon=True)
        self.worker.start()
        previous = read_json(self.state_path)
        self.previous = previous
        if previous.get("active"):
            self.emit("previous_session_interrupted", previous_session=previous.get("session"),
                      started_at=previous.get("started_at"),
                      cause="unknown; consult Windows system events")
        self.state = {"session": self.session, "started_at": timestamp(), "active": True}
        try:
            atomic_json(self.state_path, self.state)
            self.emit("session_started")
            self.flush()
        except Exception:
            self.queue.put(None)
            self.worker.join()
            self.stream.close()
            self.worker = None
            raise

    def emit(self, event, **details):
        with self._enqueue_lock:
            if self._accepting:
                self.queue.put({"time": timestamp(), "session": self.session,
                                "event": event, **details})

    def _write(self):
        while True:
            entry = self.queue.get()
            try:
                if entry is None:
                    return
                self.stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.stream.flush()
                os.fsync(self.stream.fileno())
            except Exception as exc:
                self.error = exc
            finally:
                self.queue.task_done()

    def flush(self):
        self.queue.join()
        if self.error:
            raise OSError(f"Cannot preserve audit trail: {self.error}")

    def close(self, reason="deactivated"):
        if not self.worker:
            return
        try:
            self.emit("session_ended", reason=reason)
            with self._enqueue_lock:
                self._accepting = False
            self.flush()
            atomic_json(self.state_path, {**self.state, "active": False,
                                         "ended_at": timestamp(), "reason": reason})
        finally:
            self.queue.put(None)
            self.worker.join()
            self.stream.close()
            self.worker = None
