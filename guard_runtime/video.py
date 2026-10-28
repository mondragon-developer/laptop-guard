"""Three rotating clips, committed only after frames have been recorded."""
from __future__ import annotations

import math
import os
import threading
import time
import uuid

from .storage import RuntimePaths


class VideoRing:
    def __init__(self, folder):
        self.folder = folder

    def target(self):
        # Derive the next slot from actual files: survives restarts without a counter.
        slots = []
        for number in range(1, 4):
            files = [p for p in (self.folder / f"intruder_{number}.mp4",
                                self.folder / f"intruder_{number}.avi") if p.exists()]
            if not files:
                return number
            slots.append((max(p.stat().st_mtime_ns for p in files), number))
        return min(slots)[1]

    def commit(self, temporary, slot):
        target = self.folder / f"intruder_{slot}{temporary.suffix}"
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        for suffix in (".mp4", ".avi"):
            old = self.folder / f"intruder_{slot}{suffix}"
            if old != target:
                old.unlink(missing_ok=True)
        return target


class WebcamRecorder:
    def __init__(self, config, paths=None, audit=None):
        self.config = config
        self.paths = paths or RuntimePaths()
        self.audit = audit
        self.stop_event = threading.Event()
        self._publish_lock = threading.Lock()

    def _emit(self, event, **details):
        if self.audit:
            self.audit.emit(event, **details)

    def stop(self):
        # Once this returns, a slow camera cannot publish into a later session.
        with self._publish_lock:
            self.stop_event.set()

    def record(self):
        if self.config.record_seconds <= 0:
            self._emit("video_disabled")
            return
        cap = writer = None
        temporary = None
        recording_id = uuid.uuid4().hex
        try:
            import cv2
            self.paths.ensure()
            ring = VideoRing(self.paths.videos)
            slot = ring.target()
            self._emit("video_started", slot=slot)
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise RuntimeError("No webcam available")
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                fps = 20.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
            for codec, suffix in (("mp4v", ".mp4"), ("XVID", ".avi")):
                temporary = self.paths.videos / (f"{recording_id}.pending" + suffix)
                writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*codec),
                                         fps, (width, height))
                if writer.isOpened():
                    break
                writer.release()
                writer = None
                temporary.unlink(missing_ok=True)
            if writer is None:
                raise RuntimeError("No working video codec")
            frames = 0
            started = time.monotonic()
            while time.monotonic() - started < self.config.record_seconds and not self.stop_event.is_set():
                ok, frame = cap.read()
                if ok:
                    writer.write(frame)
                    frames += 1
                else:
                    self.stop_event.wait(0.01)
            writer.release()
            writer = None
            if frames == 0:
                raise RuntimeError("Camera returned no frames; existing clips retained")
            check = cv2.VideoCapture(str(temporary))
            try:
                readable, _ = check.read() if check.isOpened() else (False, None)
                if not readable:
                    raise RuntimeError("Recorded clip is not decodable; existing clips retained")
            finally:
                check.release()
            with self._publish_lock:
                if self.stop_event.is_set():
                    self._emit("video_cancelled", frames=frames,
                               note="Existing completed clips retained")
                else:
                    target = ring.commit(temporary, slot)
                    self._emit("video_saved", file=str(target.relative_to(self.paths.root)),
                               slot=slot, frames=frames)
        except Exception as exc:
            self._emit("video_failed", error=str(exc))
        finally:
            if writer is not None:
                writer.release()
            if cap is not None:
                cap.release()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
