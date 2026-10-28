import tempfile
import unittest
from unittest.mock import Mock, patch

from guard_runtime.idle import IdlePolicy
from guard_runtime.auto_guard import eligible, settings, set_enabled, guard_busy, AutoWatcher, launch
from guard_runtime.storage import RuntimePaths, InstanceLock
from laptop_guard import LaptopGuard, InputGuard


class IdlePolicyTests(unittest.TestCase):
    def drive(self, policy, seconds, start=1, **kwargs):
        result = None
        for now in range(start, seconds + 1):
            result = policy.step(now, now, **kwargs)
        return result

    def test_fifteen_minutes_then_ten_second_warning(self):
        policy = IdlePolicy(now=0)
        self.assertEqual(self.drive(policy, 899)[0], "waiting")
        self.assertEqual(policy.step(900, 900), ("warning", 10))
        self.assertEqual(self.drive(policy, 909, start=901)[0], "warning")
        self.assertEqual(policy.step(910, 910), ("activate", 0))

    def test_keyboard_or_mouse_activity_cancels_countdown(self):
        for device in ("keyboard", "mouse"):
            with self.subTest(device=device):
                policy = IdlePolicy(now=0)
                self.drive(policy, 900)
                self.assertEqual(policy.step(901, 0), ("waiting", 900))
                self.assertIsNone(policy.warning_at)

    def test_start_does_not_use_idle_time_before_monitor_started(self):
        policy = IdlePolicy(now=100)
        self.assertEqual(policy.step(101, 5000), ("waiting", 899))

    def test_pause_lock_and_active_guard_each_reset_interval(self):
        for flags in ({"enabled": False}, {"available": False}, {"busy": True}):
            policy = IdlePolicy(now=0)
            self.drive(policy, 900)
            self.assertEqual(policy.step(901, 901, **flags)[0], "waiting")
            self.assertEqual(policy.step(902, 902), ("waiting", 899))

    def test_resume_after_sleep_requires_fresh_interval(self):
        policy = IdlePolicy(now=0)
        policy.step(1, 1)
        self.assertEqual(policy.step(4000, 4000)[0], "waiting")
        self.assertEqual(policy.step(4001, 4001), ("waiting", 899))

    def test_cancel_button_requires_another_full_interval(self):
        policy = IdlePolicy(now=0)
        self.drive(policy, 905)
        policy.reset(905)
        self.assertEqual(policy.step(906, 906), ("waiting", 899))


class AutoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = RuntimePaths(self.temp.name)
        self.paths.ensure()

    def test_enable_pause_round_trip(self):
        self.assertFalse(settings(self.paths)["enabled"])
        set_enabled(self.paths, True)
        self.assertEqual(settings(self.paths), {"enabled": True, "idle_seconds": 900})
        set_enabled(self.paths, False)
        self.assertFalse(settings(self.paths)["enabled"])

    def test_last_moment_input_or_pause_prevents_activation(self):
        detector = Mock()
        detector.desktop_available.return_value = True
        detector.seconds.return_value = 910
        set_enabled(self.paths, True)
        self.assertTrue(eligible(self.paths, detector))
        detector.seconds.return_value = 0
        self.assertFalse(eligible(self.paths, detector))
        detector.seconds.return_value = 910
        set_enabled(self.paths, False)
        self.assertFalse(eligible(self.paths, detector))

    def test_manual_guard_is_detected_via_shared_lock(self):
        self.assertFalse(guard_busy(self.paths))
        lock = InstanceLock(self.paths.logs / "guard.lock")
        lock.acquire()
        try:
            self.assertTrue(guard_busy(self.paths))
        finally:
            lock.release()
        self.assertFalse(guard_busy(self.paths))

    def test_cancelled_activation_never_starts_input_hooks(self):
        power = Mock()
        guard = LaptopGuard(paths=self.paths, alarm=Mock(), screen=Mock(),
                            power=power, recorder=Mock(), system_events=Mock())
        with patch.object(InputGuard, "start") as start:
            guard.activate(activation_reason="idle", can_activate=lambda: False)
        start.assert_not_called()
        power.prevent_shutdown.assert_not_called()

    def watcher(self):
        root, detector = Mock(), Mock()
        detector.desktop_available.return_value = True
        with patch("guard_runtime.auto_guard.tk.Label"), patch("guard_runtime.auto_guard.tk.Button"):
            watcher = AutoWatcher(root, self.paths, detector)
        watcher.policy.reset(0)
        set_enabled(self.paths, True)
        return watcher, detector

    def test_watcher_shows_warning_and_input_cancels_without_launch(self):
        watcher, detector = self.watcher()
        watcher.policy.last_poll = 899
        detector.seconds.return_value = 900
        with patch("guard_runtime.auto_guard.guard_busy", return_value=False), patch("guard_runtime.auto_guard.launch") as spawn:
            with patch("guard_runtime.auto_guard.time.monotonic", return_value=900):
                watcher.tick()
            self.assertTrue(watcher.warning_visible)
            detector.seconds.return_value = 0
            with patch("guard_runtime.auto_guard.time.monotonic", return_value=901):
                watcher.tick()
            self.assertFalse(watcher.warning_visible)
            spawn.assert_not_called()

    def test_watcher_launches_once_and_waits_for_guard_exit(self):
        watcher, detector = self.watcher()
        watcher.policy.last_poll = 909
        watcher.policy.warning_at = 900
        detector.seconds.return_value = 910
        child = Mock()
        child.poll.return_value = None
        with patch("guard_runtime.auto_guard.guard_busy", return_value=False), patch("guard_runtime.auto_guard.launch", return_value=child) as spawn:
            with patch("guard_runtime.auto_guard.time.monotonic", return_value=910):
                watcher.tick()
            with patch("guard_runtime.auto_guard.time.monotonic", return_value=911):
                watcher.tick()
            spawn.assert_called_once_with("--activate-idle")
            self.assertEqual(watcher.policy.since, 911)

    def test_independent_subprocess_preserves_packaged_resources(self):
        with patch("guard_runtime.auto_guard.subprocess.Popen") as spawn:
            launch("--watch")
        self.assertEqual(spawn.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")


if __name__ == "__main__":
    unittest.main()
