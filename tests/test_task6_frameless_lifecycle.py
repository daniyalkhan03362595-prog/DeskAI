import unittest
from unittest.mock import MagicMock, patch
from deskai.bridge.api import DesktopBridgeAPI, RESIZE_DIRECTIONS, _windows_native_drag
from deskai.bridge.lifecycle import WindowLifecycleHandler


class TestFramelessWindowAndLifecycle(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"

        self.lifecycle = WindowLifecycleHandler(self.mock_manager)
        self.mock_manager.lifecycle = self.lifecycle
        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_window_control_rejects_unknown_action(self):
        """Unknown window_control actions must raise ValueError."""
        with self.assertRaises(ValueError):
            self.api.window_control("unknown_action_xyz")

    def test_window_control_rejects_unknown_resize_direction(self):
        """Unknown resize direction must raise ValueError."""
        with self.assertRaises(ValueError):
            self.api.window_control("resize_start", direction="diagonal_nowhere")

    def test_all_semantic_and_compass_resize_directions_valid(self):
        """All supported compass and semantic directions must be accepted without ValueError."""
        expected_keys = [
            "n",
            "s",
            "w",
            "e",
            "nw",
            "ne",
            "sw",
            "se",
            "top",
            "bottom",
            "left",
            "right",
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
            "move",
        ]
        for key in expected_keys:
            self.assertIn(key, RESIZE_DIRECTIONS)
            # Must not raise ValueError
            try:
                self.api.window_control("resize_start", direction=key)
            except ValueError:
                self.fail(f"Valid direction '{key}' raised ValueError unexpectedly")

    def test_close_request_clean_vs_dirty(self):
        """close_request should close cleanly if no dirty tabs; return False if dirty."""
        self.lifecycle.has_dirty_tabs = False
        res_clean = self.api.window_control("close_request")
        self.assertTrue(res_clean)
        self.mock_window.destroy.assert_called_once()
        self.assertTrue(self.lifecycle._exit_confirmed)

        self.mock_window.destroy.reset_mock()
        self.lifecycle._exit_confirmed = False
        self.lifecycle.has_dirty_tabs = True
        res_dirty = self.api.window_control("close_request")
        self.assertFalse(res_dirty)
        self.mock_window.destroy.assert_not_called()

    def test_exit_confirmed_prevents_double_prompt(self):
        """
        When dirty tabs exist, confirm_exit then on_closing must prompt only ONCE.
        _exit_confirmed flag must prevent a second confirmation dialog on destroy.
        """
        self.lifecycle.has_dirty_tabs = True
        self.mock_window.create_confirmation_dialog.return_value = True

        # First prompt (e.g. triggered via close button or window_control)
        first_confirmed = self.lifecycle.confirm_exit()
        self.assertTrue(first_confirmed)
        self.assertTrue(getattr(self.lifecycle, "_exit_confirmed", False))

        # pywebview triggers on_closing as window is destroying
        second_confirmed = self.lifecycle.on_closing()
        self.assertTrue(second_confirmed)

        # Dialog should only have been displayed once, not twice
        self.assertEqual(self.mock_window.create_confirmation_dialog.call_count, 1)

    @patch("deskai.bridge.api.sys")
    def test_windows_native_drag_simulation(self, mock_sys):
        """Simulate Windows ctypes calls for frameless drag."""
        mock_sys.platform = "win32"
        mock_ctypes = MagicMock()
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_user32.FindWindowW.return_value = 12345

        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            result = _windows_native_drag(self.mock_window, 2)
            self.assertTrue(result)
            mock_user32.ReleaseCapture.assert_called_once()
            mock_user32.SendMessageW.assert_called_once_with(12345, 0x00A1, 2, 0)

    def test_linux_native_frameless_resize_setup(self):
        """_setup_linux_frameless_resize connects button-press-event to WebKit view."""
        mock_native = MagicMock()
        mock_wv = MagicMock()
        mock_native.get_children.return_value = [mock_wv]
        self.mock_window.native = mock_native

        mock_gi = MagicMock()
        mock_webkit = MagicMock()
        mock_webkit.WebView = type(mock_wv)
        mock_gi.WebKit2 = mock_webkit
        mock_gi.Gdk = MagicMock()

        with patch("sys.platform", "linux"):
            with patch.dict("sys.modules", {"gi.repository": mock_gi}):
                self.lifecycle._setup_linux_frameless_resize(self.mock_window)
                self.assertTrue(self.lifecycle._resize_hooked)


if __name__ == "__main__":
    unittest.main()
