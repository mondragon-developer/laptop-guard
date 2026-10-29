"""Screen lifecycle checks without displaying warnings or capturing real input."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from guard_runtime.displays import Display
from guard_runtime.diagnostics import camera_check, show
from guard_runtime.storage import InstanceLock, RuntimePaths
from laptop_guard import FakeScreen, GuardConfig, WinsoundAlarm, _make_alarm


class ScreenTests(unittest.TestCase):
    def simulate(self, layouts, *, preview=None, stop_after=3, failure=None):
        root = Mock()
        callbacks = []
        clock = [0]
        created = []
        def after(delay, callback):
            callbacks.append(callback)
            return len(callbacks)
        def loop():
            for step in range(1, 10):
                clock[0] = step
                if not callbacks:
                    break
                callbacks.pop(0)()
        def window(parent):
            widget = Mock()
            created.append(widget)
            return widget
        root.after.side_effect = after
        root.mainloop.side_effect = loop
        scan = Mock(side_effect=layouts)
        with patch("laptop_guard.tk.Toplevel", side_effect=window), \
             patch("guard_runtime.alert_view.WarningView"), patch("laptop_guard.tk.Button") as button, \
             patch("laptop_guard.time.monotonic", side_effect=lambda: clock[0]), \
             patch("guard_runtime.displays.monitors", scan), \
             patch("guard_runtime.displays.place", side_effect=failure) as place, \
             patch("laptop_guard._bring_app_forward"), \
             patch("laptop_guard.InputGuard") as input_guard:
            screen = FakeScreen(GuardConfig(), root)
            screen.show(should_close=lambda: clock[0] >= stop_after,
                        preview_seconds=preview)
            input_guard.assert_not_called()
        return root, created, place, button

    def test_hotplug_negative_positions_removes_obsolete_windows(self):
        primary = Display(0, 0, 1920, 1080)
        left = Display(-1920, -120, 1920, 1080)
        portrait = Display(1920, 0, 1080, 1920)
        root, windows, place, button = self.simulate(
            [(primary, left), (primary, portrait), (primary, portrait)])
        self.assertEqual([c.args[1] for c in place.call_args_list], [primary, left, portrait])
        self.assertEqual(len(windows), 3)
        for window in windows:
            window.destroy.assert_called_once()
        button.assert_not_called()
        root.destroy.assert_not_called()  # shared Tk survives

    def test_preview_times_out_and_has_escape_and_close_buttons(self):
        display = Display(0, 0, 800, 600)
        root, windows, place, button = self.simulate(
            [(display,), (display,)], preview=2, stop_after=8)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].bind.call_args.args[0], "<Escape>")
        button.assert_called_once()
        root.quit.assert_called_once()
        windows[0].destroy.assert_called_once()

    def test_unlock_before_screen_show_never_opens_window(self):
        screen = FakeScreen(GuardConfig(), Mock())
        screen.deactivate()
        with patch("laptop_guard.tk.Toplevel") as window:
            screen.show()
        window.assert_not_called()

    def test_placement_failure_cleans_up_and_propagates(self):
        with self.assertRaisesRegex(OSError, "placement failed"):
            self.simulate([(Display(0, 0, 800, 600),)], failure=OSError("placement failed"))

    def test_windows_does_not_construct_pygame(self):
        with patch("laptop_guard.platform.system", return_value="Windows"), \
             patch("laptop_guard.PygameAlarm") as pygame:
            self.assertIsInstance(_make_alarm(), WinsoundAlarm)
            pygame.assert_not_called()

    def test_stopped_alarm_never_beeps(self):
        alarm = WinsoundAlarm()
        alarm.stop()
        sound = Mock()
        with patch.dict("sys.modules", {"winsound": sound}):
            alarm.play(10)
        sound.Beep.assert_not_called()

    def test_camera_test_uses_and_removes_temporary_evidence(self):
        observed = []
        def recorder(config, paths):
            observed.append(paths.root)
            self.assertEqual(config.record_seconds, 2)
            def record():
                paths.ensure()
                (paths.videos / "intruder_1.mp4").write_bytes(b"test")
            return Mock(record=record)
        original = GuardConfig(record_seconds=9)
        with patch("guard_runtime.diagnostics.WebcamRecorder", side_effect=recorder):
            self.assertIn("correctas", camera_check(original, Mock()))
        self.assertEqual(original.record_seconds, 9)
        self.assertFalse(observed[0].exists())

    def test_camera_failure_is_reported_and_temporary_folder_removed(self):
        observed = []
        def recorder(config, paths):
            observed.append(paths.root)
            return Mock()
        with patch("guard_runtime.diagnostics.WebcamRecorder", side_effect=recorder):
            with self.assertRaisesRegex(RuntimeError, "cámara"):
                camera_check(GuardConfig(), Mock())
        self.assertFalse(observed[0].exists())

    def test_diagnostics_holds_guard_lock_and_never_arms(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = RuntimePaths(folder)
            root = Mock()
            root.winfo_children.return_value = []
            def mainloop():
                competing = InstanceLock(paths.logs / "guard.lock")
                with self.assertRaises(RuntimeError):
                    competing.acquire()
            root.mainloop.side_effect = mainloop
            with patch("guard_runtime.diagnostics.tk.Label"), \
                 patch("guard_runtime.diagnostics.tk.Button"), \
                 patch("laptop_guard.InputGuard") as listener, \
                 patch("laptop_guard.LaptopGuard") as guard:
                show(root, GuardConfig(), paths)
                listener.assert_not_called()
                guard.assert_not_called()
            available = InstanceLock(paths.logs / "guard.lock")
            available.acquire()
            available.release()

    def test_completion_is_published_after_camera_is_released(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Mock()
            root.winfo_children.return_value = []
            resource = Mock()
            messages = Mock()
            messages.put.side_effect = lambda result: resource.stop.assert_called_once()
            # Make queue polling see no completed result before the button press.
            import queue
            messages.get_nowait.side_effect = queue.Empty
            def check(config, register):
                register(resource)
                return "ok"
            def synchronous_thread(*, target, daemon):
                return Mock(start=target)
            with patch("guard_runtime.diagnostics.tk.Label"), \
                 patch("guard_runtime.diagnostics.tk.Button") as buttons, \
                 patch("guard_runtime.diagnostics.queue.Queue", return_value=messages), \
                 patch("guard_runtime.diagnostics.camera_check", side_effect=check), \
                 patch("guard_runtime.diagnostics.threading.Thread", side_effect=synchronous_thread):
                def click_camera():
                    for call in buttons.call_args_list:
                        if call.kwargs["text"].startswith("Probar cámara"):
                            call.kwargs["command"]()
                            return
                    self.fail("Camera test button missing")
                root.mainloop.side_effect = click_camera
                show(root, GuardConfig(), RuntimePaths(folder))
            messages.put.assert_called_once_with("ok")
