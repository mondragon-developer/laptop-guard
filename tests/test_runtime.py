"""Hardware-free checks: no real input hooks, camera, alarm or shutdown."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from guard_runtime.audit import AuditLog
from guard_runtime.storage import RuntimePaths, InstanceLock, atomic_json, read_json
from guard_runtime.system_events import SystemEvents, parse_events
from guard_runtime.video import VideoRing, WebcamRecorder
from laptop_guard import GuardConfig, InputGuard, LaptopGuard


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = RuntimePaths(self.temporary.name)
        self.paths.ensure()

    def entries(self):
        return [json.loads(line) for line in
                (self.paths.logs / "guard.jsonl").read_text(encoding="utf-8").splitlines() if line]

    def test_logs_append_across_sessions_and_recover_interruption(self):
        atomic_json(self.paths.logs / "session.json", {"active": True, "session": "crashed"})
        for number in range(2):
            audit = AuditLog(self.paths)
            audit.start()
            audit.emit("input_attempt", source="key:press", count=number + 1)
            audit.close()
        entries = self.entries()
        self.assertEqual(sum(e["event"] == "previous_session_interrupted" for e in entries), 1)
        self.assertEqual(sum(e["event"] == "session_started" for e in entries), 2)
        self.assertEqual(sum(e["event"] == "input_attempt" for e in entries), 2)
        self.assertFalse(read_json(self.paths.logs / "session.json")["active"])
        self.assertIn("T", entries[0]["time"])

    def test_concurrent_events_produce_valid_complete_lines(self):
        audit = AuditLog(self.paths)
        audit.start()
        workers = [threading.Thread(target=lambda: [audit.emit("input_attempt") for _ in range(25)]) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        audit.close()
        self.assertEqual(sum(e["event"] == "input_attempt" for e in self.entries()), 100)

    def test_write_failure_keeps_session_open_for_recovery(self):
        audit = AuditLog(self.paths)
        audit.start()
        audit.stream.close()
        audit.emit("will_fail")
        with self.assertRaises(OSError):
            audit.close()
        self.assertTrue(read_json(self.paths.logs / "session.json")["active"])

    def test_only_three_clips_survive_seven_recordings_and_codec_change(self):
        slots = []
        for i in range(7):
            ring = VideoRing(self.paths.videos)  # New instance: simulate restarting app.
            slot = ring.target()
            slots.append(slot)
            suffix = ".mp4" if i % 2 else ".avi"
            temporary = self.paths.videos / ("recording.pending" + suffix)
            temporary.write_bytes(f"clip-{i}".encode())
            target = ring.commit(temporary, slot)
            os.utime(target, (1000 + i, 1000 + i))
        self.assertEqual(slots, [1, 2, 3, 1, 2, 3, 1])
        self.assertEqual(sorted(p.read_bytes() for p in self.paths.videos.iterdir()),
                         [b"clip-4", b"clip-5", b"clip-6"])

    def test_camera_failure_does_not_replace_old_clips(self):
        existing = self.paths.videos / "intruder_1.mp4"
        existing.write_bytes(b"existing")
        cv2 = Mock()
        cv2.VideoCapture.return_value.isOpened.return_value = False
        audit = Mock()
        with patch.dict("sys.modules", {"cv2": cv2}):
            WebcamRecorder(GuardConfig(), self.paths, audit).record()
        self.assertEqual(existing.read_bytes(), b"existing")
        cv2.VideoCapture.return_value.release.assert_called_once()
        self.assertTrue(any(c.args[0] == "video_failed" for c in audit.emit.call_args_list))

    def test_no_frames_keeps_previous_video(self):
        existing = self.paths.videos / "intruder_1.mp4"
        existing.write_bytes(b"existing")
        cv2 = Mock()
        cap = cv2.VideoCapture.return_value
        cap.get.return_value = 20
        cap.read.return_value = (False, None)
        cv2.VideoWriter.return_value.isOpened.return_value = True
        recorder = WebcamRecorder(GuardConfig(record_seconds=0.01), self.paths, Mock())
        with patch.dict("sys.modules", {"cv2": cv2}):
            recorder.record()
        self.assertEqual(existing.read_bytes(), b"existing")
        self.assertEqual(len(list(self.paths.videos.iterdir())), 1)

    def test_successful_recording_fallback_is_avi_and_logged(self):
        audit = Mock()
        recorder = WebcamRecorder(GuardConfig(record_seconds=0.01), self.paths, audit)
        cv2 = Mock()
        cap = cv2.VideoCapture.return_value
        cap.get.return_value = 20
        def read_frame():
            import time
            time.sleep(0.02)
            return True, b"frame"
        cap.read.side_effect = read_frame
        failed = Mock()
        failed.isOpened.return_value = False
        good = Mock()
        good.isOpened.return_value = True
        def make_writer(path, *args):
            Path(path).write_bytes(b"video")
            return failed if path.endswith("mp4") else good
        cv2.VideoWriter.side_effect = make_writer
        with patch.dict("sys.modules", {"cv2": cv2}):
            recorder.record()
        self.assertTrue((self.paths.videos / "intruder_1.avi").exists())
        self.assertEqual(len(list(self.paths.videos.iterdir())), 1)
        saved = [c for c in audit.emit.call_args_list if c.args[0] == "video_saved"][0]
        self.assertEqual(saved.kwargs["frames"], 1)
        self.assertTrue(saved.kwargs["file"].endswith(".avi"))

    def test_cancelled_slow_camera_never_replaces_video(self):
        audit = Mock()
        recorder = WebcamRecorder(GuardConfig(record_seconds=1), self.paths, audit)
        cv2 = Mock()
        cap = cv2.VideoCapture.return_value
        cap.get.return_value = 20
        def read_frame():
            recorder.stop()
            return True, b"frame"
        cap.read.side_effect = read_frame
        def writer(path, *args):
            Path(path).write_bytes(b"partial")
            return Mock()
        cv2.VideoWriter.side_effect = writer
        with patch.dict("sys.modules", {"cv2": cv2}):
            recorder.record()
        self.assertFalse(list(self.paths.videos.iterdir()))
        self.assertIn("video_cancelled", [c.args[0] for c in audit.emit.call_args_list])

    def test_late_producer_after_close_cannot_queue_unwritten_event(self):
        audit = AuditLog(self.paths)
        audit.start()
        audit.close()
        audit.emit("late")
        self.assertTrue(audit.queue.empty())

    def test_corrupt_encoded_video_does_not_replace_existing_clip(self):
        original = self.paths.videos / "intruder_1.mp4"
        original.write_bytes(b"good previous clip")
        audit = Mock()
        recorder = WebcamRecorder(GuardConfig(record_seconds=0.01), self.paths, audit)
        cv2 = Mock()
        camera, decoder = Mock(), Mock()
        camera.get.return_value = 20
        camera.read.return_value = (True, b"frame")
        decoder.read.return_value = (False, None)
        cv2.VideoCapture.side_effect = [camera, decoder]
        def writer(path, *args):
            Path(path).write_bytes(b"corrupt header")
            return Mock()
        cv2.VideoWriter.side_effect = writer
        with patch.dict("sys.modules", {"cv2": cv2}):
            recorder.record()
        self.assertEqual(original.read_bytes(), b"good previous clip")
        self.assertEqual(len(list(self.paths.videos.iterdir())), 1)
        self.assertIn("video_failed", [c.args[0] for c in audit.emit.call_args_list])

    def test_instance_lock_released_on_close(self):
        first = InstanceLock(self.paths.logs / "guard.lock")
        second = InstanceLock(self.paths.logs / "guard.lock")
        first.acquire()
        try:
            with self.assertRaises(RuntimeError):
                second.acquire()
        finally:
            first.release()
        second.acquire()
        second.release()

    def test_orchestrator_unlock_closes_audit_and_releases_resources(self):
        alarm, screen, power, recorder, system = [Mock() for _ in range(5)]
        guard = LaptopGuard(paths=self.paths, alarm=alarm, screen=screen,
                            power=power, recorder=recorder, system_events=system)
        input_completed = threading.Event()
        def show_until_unlock(should_close):
            # The real screen waits for deactivation. An immediate-return Mock
            # races the input thread and can stop it halfway through the combo.
            self.assertTrue(input_completed.wait(3), "Simulated unlock timed out")
            self.assertTrue(should_close())
        screen.show.side_effect = show_until_unlock
        def simulated_input(input_guard):
            try:
                input_guard._handle_mouse("click")
                for key in ("ctrl", "shift", "z"):
                    input_guard._handle_press(key)
            finally:
                input_completed.set()
        with patch.object(InputGuard, "start", simulated_input):
            self.assertIsNone(guard.activate())
        events = [item["event"] for item in self.entries()]
        self.assertIn("alarm_triggered", events)
        self.assertIn("guard_unlocked", events)
        self.assertEqual(events[-1], "session_ended")
        self.assertFalse(read_json(self.paths.logs / "session.json")["active"])
        power.restore.assert_called_once()
        system.stop.assert_called_once()
        recorder.stop.assert_called_once()

    def test_long_configured_clip_receives_full_shutdown_grace(self):
        guard = LaptopGuard(GuardConfig(record_seconds=60), paths=self.paths,
                            alarm=Mock(), screen=Mock(), power=Mock(),
                            recorder=Mock(), system_events=Mock())
        video_thread = Mock()
        video_thread.name = "guard-video"
        video_thread.is_alive.return_value = False
        guard._media_threads = [video_thread]
        def immediate_unlock(input_guard):
            input_guard._active = False
            input_guard._on_deact()
        with patch.object(InputGuard, "start", immediate_unlock):
            guard.activate()
        video_thread.join.assert_called_once_with(timeout=65)

    def test_native_codec_four_clips_without_real_camera(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("Optional OpenCV/numpy unavailable")
        import time
        real_capture = cv2.VideoCapture
        class SyntheticCamera:
            def isOpened(self):
                return True
            def get(self, prop):
                return {cv2.CAP_PROP_FPS: 20, cv2.CAP_PROP_FRAME_WIDTH: 64,
                        cv2.CAP_PROP_FRAME_HEIGHT: 48}.get(prop, 0)
            def read(self):
                time.sleep(0.01)
                return True, np.zeros((48, 64, 3), dtype=np.uint8)
            def release(self):
                pass
        audit = Mock()
        def capture(source):
            return SyntheticCamera() if source == 0 else real_capture(source)
        with patch.object(cv2, "VideoCapture", side_effect=capture):
            for _ in range(4):
                WebcamRecorder(GuardConfig(record_seconds=0.04), self.paths, audit).record()
        files = list(self.paths.videos.iterdir())
        failures = [call.kwargs for call in audit.emit.call_args_list if call.args[0] == "video_failed"]
        self.assertEqual(len(files), 3, failures)
        self.assertEqual(sum(c.args[0] == "video_saved" for c in audit.emit.call_args_list), 4)
        for path in files:
            clip = real_capture(str(path))
            try:
                self.assertTrue(clip.read()[0])
            finally:
                clip.release()


class InputTests(unittest.TestCase):
    def setUp(self):
        self.trigger, self.unlock, self.log = Mock(), Mock(), Mock()
        self.guard = InputGuard(GuardConfig(), self.trigger, self.unlock, self.log)

    def test_trigger_once_unlock_and_no_secret_in_log(self):
        for key in ("a", "ctrl", "shift", "z"):
            self.guard._handle_press(key)
        self.trigger.assert_called_once()
        self.unlock.assert_called_once()
        self.assertFalse(self.guard.is_active)
        self.assertEqual([c.args[0] for c in self.log.call_args_list], ["key:press"] * 3)

    def test_windows_control_character_normalization(self):
        self.assertEqual(InputGuard._key_name(SimpleNamespace(char="\x1a")), "z")

    def test_mouse_counts_and_scroll_after_alarm(self):
        for _ in range(100):
            self.guard._handle_mouse("move")
        self.guard._handle_mouse("click")
        self.guard._handle_mouse("scroll")
        self.guard.stop()
        sources = [c.args[0] for c in self.log.call_args_list]
        self.assertEqual(sum(int(s.split(":")[2]) for s in sources if s.startswith("mouse:move:")), 100)
        self.assertIn("mouse:scroll", sources)
        self.assertIn("mouse:click", sources)
        self.trigger.assert_called_once()

    def test_listener_exception_deactivates(self):
        with patch("laptop_guard.sys.platform", "win32"), patch.object(self.guard, "_start_pynput", side_effect=RuntimeError("hook failed")), patch("laptop_guard.log_debug"):
            self.guard.start()
        self.assertFalse(self.guard.is_active)
        self.assertEqual(self.guard.failure, "hook failed")
        self.unlock.assert_called_once()


class SystemEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = RuntimePaths(self.temp.name)
        self.paths.ensure()
        self.audit = Mock()

    def event(self, record_id, kind="system_started"):
        return {"record_id": record_id, "occurred_at": f"2026-10-28T01:{record_id}:00Z",
                "observed_event": kind, "event_id": 12, "provider": "Microsoft-Windows-Kernel-General", "data": {}}

    def test_xml_keeps_os_time_reason_and_shutdown_type(self):
        xml = '''<Events><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System><Provider Name="User32"/><EventID>1074</EventID><TimeCreated SystemTime="2026-10-28T12:00:00Z"/><EventRecordID>23</EventRecordID></System><EventData><Data Name="param5">restart</Data><Data Name="param7">user</Data></EventData></Event></Events>'''
        event = parse_events(xml)[0]
        self.assertEqual(event["observed_event"], "shutdown_or_restart_requested")
        self.assertEqual(event["data"]["param5"], "restart")
        self.assertEqual(event["occurred_at"], "2026-10-28T12:00:00Z")

    def test_recovery_imports_and_does_not_duplicate_next_launch(self):
        base, top = self.event(10), self.event(13)
        atomic_json(self.paths.logs / "windows_cursor.json", base)
        query = Mock(side_effect=[[top], [base], [self.event(11), self.event(12), top], []])
        monitor = SystemEvents(self.paths, self.audit, query)
        monitor.poll()
        self.assertEqual(sum(c.args[0] == "windows_system_event" for c in self.audit.emit.call_args_list), 3)
        self.assertEqual(read_json(monitor.path)["record_id"], 13)
        self.audit.reset_mock()
        monitor = SystemEvents(self.paths, self.audit, Mock(side_effect=[[top], [top], []]))
        monitor.poll()
        self.audit.emit.assert_not_called()

    def test_failed_log_flush_does_not_advance_disk_cursor(self):
        base, top = self.event(1), self.event(2)
        atomic_json(self.paths.logs / "windows_cursor.json", base)
        self.audit.flush.side_effect = OSError("full disk")
        monitor = SystemEvents(self.paths, self.audit, Mock(side_effect=[[top], [base], [top]]))
        with self.assertRaises(OSError):
            monitor.poll()
        self.assertEqual(read_json(monitor.path)["record_id"], 1)

    def test_first_start_sets_baseline_without_importing_old_history(self):
        monitor = SystemEvents(self.paths, self.audit, Mock(return_value=[self.event(42)]))
        monitor.poll()
        self.assertEqual(read_json(monitor.path)["record_id"], 42)
        self.assertEqual(self.audit.emit.call_args.args[0], "windows_history_baseline")

    def test_cleared_journal_is_reported(self):
        atomic_json(self.paths.logs / "windows_cursor.json", self.event(100))
        top = self.event(5)
        monitor = SystemEvents(self.paths, self.audit, Mock(side_effect=[[top], [], [top], []]))
        monitor.poll()
        self.assertIn("windows_history_gap", [c.args[0] for c in self.audit.emit.call_args_list])

    def test_no_cursor_recovers_from_interrupted_first_session_start(self):
        self.audit.previous = {"active": True, "started_at": "2026-10-27T08:00:00-04:00"}
        top = self.event(50)
        query = Mock(side_effect=[[top], [top], []])
        monitor = SystemEvents(self.paths, self.audit, query)
        monitor.poll()
        self.assertIn("TimeCreated[@SystemTime>='2026-10-27T12:00:00Z']", query.call_args_list[1].args[0])
        self.assertIn("windows_system_event", [c.args[0] for c in self.audit.emit.call_args_list])


if __name__ == "__main__":
    unittest.main()
