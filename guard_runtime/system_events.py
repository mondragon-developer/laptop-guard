"""Recover Windows power events from the OS journal, including across restarts.

This observes system evidence, not a person's intent or identity. No service,
scheduled task, or automatic guard activation is installed.
"""
from __future__ import annotations

import os
import subprocess
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .storage import atomic_json, read_json

EVENTS = {
    ("User32", 1074): "shutdown_or_restart_requested",
    ("Microsoft-Windows-User32", 1074): "shutdown_or_restart_requested",
    ("EventLog", 6005): "event_log_service_started",
    ("EventLog", 6006): "event_log_service_stopped",
    ("EventLog", 6008): "unexpected_shutdown_reported",
    ("Microsoft-Windows-Kernel-Power", 41): "unclean_restart_reported",
    ("Microsoft-Windows-Kernel-Power", 42): "sleep_entered",
    ("Microsoft-Windows-Kernel-General", 12): "system_started",
    ("Microsoft-Windows-Kernel-General", 13): "system_shutdown_started",
    ("Microsoft-Windows-Power-Troubleshooter", 1): "system_resumed",
}


def parse_events(xml):
    root = ET.fromstring(xml)
    result = []
    for event in root:
        ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
        system = event.find("e:System", ns)
        provider = system.find("e:Provider", ns).get("Name")
        event_id = int(system.findtext("e:EventID", namespaces=ns))
        record_id = int(system.findtext("e:EventRecordID", namespaces=ns))
        data = {item.get("Name", str(i)): item.text or ""
                for i, item in enumerate(event.findall("e:EventData/e:Data", ns))}
        result.append({"record_id": record_id, "event_id": event_id,
                       "provider": provider,
                       "observed_event": EVENTS.get((provider, event_id), "other"),
                       "occurred_at": system.find("e:TimeCreated", ns).get("SystemTime"),
                       "data": data})
    return result


def query_events(xpath, count=256, newest=False):
    # wevtutil is installed with Windows; XML avoids localized message parsing.
    result = subprocess.run(
        ["wevtutil", "qe", "System", f"/q:{xpath}", f"/c:{count}",
         f"/rd:{str(newest).lower()}", "/f:xml", "/e:Events"],
        capture_output=True, timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise OSError(result.stderr.decode("utf-8", errors="replace").strip())
    raw = result.stdout
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        xml = raw.decode("utf-16")
    else:
        xml = raw.decode("utf-8-sig")
    return parse_events(xml) if xml.strip() else []


class SystemEvents:
    def __init__(self, paths, audit, query=query_events):
        self.audit = audit
        self.path = paths.logs / "windows_cursor.json"
        self.query = query
        self.stop_event = threading.Event()
        self.thread = None
        self.cursor = read_json(self.path)
        self.last_error = None

    def poll(self):
        latest = self.query("*", count=1, newest=True)
        if not latest:
            return
        top = latest[0]
        cursor_id = int(self.cursor.get("record_id", 0))
        time_filter = ""
        if not self.cursor:
            previous = getattr(self.audit, "previous", {})
            current = getattr(self.audit, "state", {})
            state = previous if isinstance(previous, dict) and previous.get("active") else current
            since = state.get("started_at") if isinstance(state, dict) else None
            self.audit.emit("windows_history_baseline", record_id=top["record_id"],
                            monitoring_started_at=since,
                            note="Earlier unrelated history is not imported.")
            self.audit.flush()
            if not since:
                self._save(top)
                return
            utc = datetime.fromisoformat(since).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            time_filter = f" and TimeCreated[@SystemTime>='{utc}']"
        # Compare the anchor timestamp too: record IDs can be reused after clear.
        if self.cursor:
            anchor = self.query(f"*[System[EventRecordID={cursor_id}]]", count=1)
            if top["record_id"] < cursor_id or not anchor or anchor[0]["occurred_at"] != self.cursor.get("occurred_at"):
                self.audit.emit("windows_history_gap", previous_record_id=cursor_id,
                                note="System journal was cleared or older records expired.")
                cursor_id = 0
        ids = " or ".join(f"EventID={i}" for i in sorted({key[1] for key in EVENTS}))
        while not self.stop_event.is_set():
            batch = self.query(f"*[System[EventRecordID>{cursor_id} and EventRecordID<={top['record_id']} and ({ids}){time_filter}]]")
            if not batch:
                break
            for item in batch:
                if item["observed_event"] != "other":
                    self.audit.emit("windows_system_event", **item)
            # Persist the cursor only after evidence has reached the log file.
            self.audit.flush()
            self._save(batch[-1])
            cursor_id = batch[-1]["record_id"]
        if not self.stop_event.is_set():
            self.audit.flush()
            self._save(top)

    def _save(self, item):
        self.cursor = {"record_id": item["record_id"], "occurred_at": item["occurred_at"]}
        atomic_json(self.path, self.cursor)

    def start(self):
        if os.name != "nt":
            self.audit.emit("system_history_unavailable", platform=os.name)
            return
        self._poll_safely()  # Establish/recover evidence before input hooks activate.
        self.thread = threading.Thread(target=self._run, name="guard-system-events", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.wait(5):
            self._poll_safely()

    def _poll_safely(self):
        try:
            self.poll()
            if self.last_error:
                self.audit.emit("system_history_restored")
            self.last_error = None
        except Exception as exc:
            if str(exc) != self.last_error:
                self.audit.emit("system_history_error", error=str(exc))
            self.last_error = str(exc)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()  # Each OS query has a bounded timeout.
