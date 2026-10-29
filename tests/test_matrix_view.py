"""Check bounded animation and display options without a desktop or input hooks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from guard_runtime.alert_view import MatrixRain, WarningView, MAX_COLUMNS
from guard_runtime.warning import warning_state
from laptop_guard import GuardConfig, load_config, save_config


class MatrixTests(unittest.TestCase):
    def canvas(self):
        canvas = Mock()
        canvas.create_text.side_effect = range(1, 10000)
        return canvas

    def test_four_k_rain_has_fixed_pool_and_reuses_items(self):
        canvas = self.canvas()
        rain = MatrixRain(canvas)
        rain.resize(3840, 2160)
        self.assertEqual(canvas.create_text.call_count, MAX_COLUMNS * 3)
        for frame in range(100):
            rain.render(frame / 10)
        self.assertEqual(canvas.create_text.call_count, MAX_COLUMNS * 3)
        self.assertEqual(canvas.delete.call_count, 1)
        # Resize discards the old pool; it never appends to the existing one.
        rain.resize(800, 600)
        self.assertEqual(len(rain.columns), 800 // 38)
        self.assertEqual(canvas.delete.call_count, 2)

    def test_glyphs_change_only_twice_a_second(self):
        canvas = self.canvas()
        rain = MatrixRain(canvas)
        rain.resize(800, 600)
        rain.render(0)
        updates = canvas.itemconfigure.call_count
        rain.render(0.1)
        self.assertEqual(canvas.itemconfigure.call_count, updates)
        rain.render(0.5)
        self.assertEqual(canvas.itemconfigure.call_count, updates * 2)

    def test_matrix_disabled_has_no_rain_and_no_extra_timer(self):
        canvas, window = self.canvas(), Mock()
        with patch('guard_runtime.alert_view.tk.Canvas', return_value=canvas):
            view = WarningView(window, GuardConfig(matrix_background=False), 800, 600)
            self.assertIsNone(view.rain)
            view.render(1, warning_state(1))
        canvas.itemconfigure.assert_any_call(view.background_code, state='hidden')
        canvas.after.assert_not_called()
        window.after.assert_not_called()

    def test_effects_disabled_and_custom_message_are_preserved(self):
        canvas = self.canvas()
        config = GuardConfig(message='Custom warning', show_simulation=False, matrix_background=False)
        with patch('guard_runtime.alert_view.tk.Canvas', return_value=canvas):
            view = WarningView(Mock(), config, 800, 600, standard_message=False)
        for item in (view.prompt, view.phone, view.action, view.timer, view.console, view.footer):
            canvas.itemconfigure.assert_any_call(item, state='hidden')
        self.assertTrue(any(call.kwargs.get('text') == 'Custom warning' for call in canvas.create_text.call_args_list))

    def test_expiry_fits_timer_and_does_not_reveal_unlock_combination(self):
        canvas = self.canvas()
        config = GuardConfig(phone='DEMO CONTACT', key_combo=('ctrl', 'alt', 'secret'))
        with patch('guard_runtime.alert_view.tk.Canvas', return_value=canvas):
            view = WarningView(Mock(), config, 800, 600)
            view.render(120, warning_state(120))
        canvas.itemconfigure.assert_any_call(view.timer, fill=warning_state(120).color, text='00:00')
        text = ' '.join(str(call.kwargs.get('text', '')) for call in canvas.create_text.call_args_list)
        self.assertIn('DEMO CONTACT', text)
        self.assertNotIn('secret', text)

    def test_existing_config_defaults_and_disabled_option_survive_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'config.json')
            save_config({'phone': 'EXAMPLE'}, path)
            self.assertTrue(load_config(path).matrix_background)
            save_config({'phone': 'EXAMPLE', 'matrix_background': False}, path)
            self.assertFalse(load_config(path).matrix_background)
