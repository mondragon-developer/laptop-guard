"""Alarm cancellation and visual-only effects, without audio or real input."""
from array import array
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from unittest.mock import Mock, patch

from guard_runtime.audio import pcm_tone, write_alarm, SAMPLE_RATE
from guard_runtime.warning import warning_state
from laptop_guard import PygameAlarm, WindowsSirenAlarm, WinsoundAlarm, _make_alarm, load_config, save_config


class AlertTests(unittest.TestCase):
    def sound_mock(self):
        return Mock(SND_FILENAME=1, SND_ASYNC=2, SND_LOOP=4)

    def test_classic_wave_matches_original_frequency_amplitude_and_duration(self):
        samples = array("h", pcm_tone())[::2]
        self.assertEqual(len(samples), SAMPLE_RATE)
        self.assertEqual(set(samples), {-16000, 16000})
        crossings = sum((a < 0) != (b < 0) for a, b in zip(samples, samples[1:]))
        self.assertEqual(crossings, 1599)  # 800 square-wave cycles / second
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alarm.wav"
            write_alarm(path)
            with wave.open(str(path)) as stream:
                self.assertEqual((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()),
                                 (2, 2, 44100, 44100))

    def test_beep_tone_is_distinct_without_changing_duration(self):
        self.assertEqual(len(pcm_tone("beep")), len(pcm_tone()))
        self.assertNotEqual(pcm_tone("beep"), pcm_tone())

    def test_windows_choice_does_not_load_pygame(self):
        with patch("laptop_guard.platform.system", return_value="Windows"), patch("laptop_guard.PygameAlarm") as pygame:
            self.assertIsInstance(_make_alarm(), WindowsSirenAlarm)
            self.assertIs(type(_make_alarm("beep")), WinsoundAlarm)
            pygame.assert_not_called()

    def test_unlock_stops_async_playback_and_removes_temporary_wave(self):
        alarm, sound, started = WindowsSirenAlarm(), self.sound_mock(), threading.Event()
        files = []
        def play(path, flags):
            if path:
                self.assertTrue(Path(path).exists())
                files.append(Path(path))
                started.set()
        sound.PlaySound.side_effect = play
        with patch.dict("sys.modules", {"winsound": sound}):
            worker = threading.Thread(target=alarm.play, args=(60,))
            worker.start()
            try:
                self.assertTrue(started.wait(3))
            finally:
                alarm.stop()
                worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(sound.PlaySound.call_args.args, (None, 0))
        self.assertTrue(files)
        self.assertFalse(files[0].exists())

    def test_unlock_during_wave_generation_never_starts_audio(self):
        alarm, sound = WindowsSirenAlarm(), self.sound_mock()
        with patch.dict("sys.modules", {"winsound": sound}), \
             patch("guard_runtime.audio.write_alarm", side_effect=lambda path: alarm.stop()):
            alarm.play(60)
        sound.PlaySound.assert_not_called()

    def test_expired_duration_stops_audio_without_unlock(self):
        alarm, sound = WindowsSirenAlarm(), self.sound_mock()
        with patch.dict("sys.modules", {"winsound": sound}), patch.object(alarm._stop, "wait") as wait:
            alarm.play(7)
        wait.assert_called_once_with(7)
        self.assertEqual(sound.PlaySound.call_args.args, (None, 0))

    def test_wave_failure_falls_back_to_beeps(self):
        alarm, sound = WindowsSirenAlarm(), self.sound_mock()
        sound.PlaySound.side_effect = RuntimeError("audio unavailable")
        with patch.dict("sys.modules", {"winsound": sound}), \
             patch.object(WinsoundAlarm, "play") as fallback, patch("laptop_guard.log_debug"):
            alarm.play(7)
        fallback.assert_called_once_with(7)

    def test_mac_unlock_serializes_with_play_and_stops_the_sound(self):
        pygame, sound = Mock(), Mock()
        pygame.mixer.Sound.return_value = sound
        started, release_play = threading.Event(), threading.Event()
        def play(**kwargs):
            started.set()
            release_play.wait(3)
        sound.play.side_effect = play
        with patch.dict("sys.modules", {"pygame": pygame}):
            alarm = PygameAlarm()
            worker = threading.Thread(target=alarm.play, args=(60,))
            stopper = threading.Thread(target=alarm.stop)
            worker.start()
            try:
                self.assertTrue(started.wait(3))
                stopper.start()
                self.assertTrue(alarm._stop.wait(3))
                sound.stop.assert_not_called()
            finally:
                release_play.set()
                worker.join(3)
                if stopper.ident:
                    stopper.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(stopper.is_alive())
        sound.stop.assert_called_once()

    def test_existing_config_and_optional_effects_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "config.json")
            save_config({"phone": "EXAMPLE", "alarm_duration_sec": 19}, path)
            old = load_config(path)
            self.assertEqual((old.phone, old.alarm_duration_sec, old.alarm_style), ("EXAMPLE", 19, "siren"))
            save_config({"alarm_style": "beep", "flash_warning": False, "show_simulation": False}, path)
            cfg = load_config(path)
            self.assertEqual((cfg.alarm_style, cfg.flash_warning, cfg.show_simulation), ("beep", False, False))
            save_config({"alarm_style": "unknown"}, path)
            self.assertEqual(load_config(path).alarm_style, "siren")

    def test_countdown_is_bounded_and_expiration_is_only_visual(self):
        self.assertIn("02:00", warning_state(-1).countdown)
        self.assertIn("01:59", warning_state(1).countdown)
        self.assertIn("00:01", warning_state(119.9).countdown)
        for elapsed in (120, 121, 10000):
            state = warning_state(elapsed)
            self.assertIn("00:00", state.countdown)
            self.assertIn("No files were changed", state.console)
        self.assertIn("demo_file_", warning_state(0).console)

    def test_effects_can_be_disabled_independently(self):
        self.assertNotEqual(warning_state(0).color, warning_state(0.7).color)
        self.assertEqual(warning_state(0, flash=False).color, warning_state(0.7, flash=False).color)
        state = warning_state(1, simulation=False)
        self.assertEqual((state.countdown, state.console), ("", ""))
