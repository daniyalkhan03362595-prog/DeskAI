"""
Window Chrome & Frameless Window Controls Bridge Module.
Handles min, max, close, frameless drag, resize, and buffer dirty status.
"""

import logging
import sys
import webview
from deskai.bridge.base import BaseBridgeModule

logger = logging.getLogger(__name__)

# Windows Hit-Test Codes & Semantic Resize Direction Mapping
RESIZE_DIRECTIONS = {
    "n": 12,
    "s": 15,
    "w": 10,
    "e": 11,
    "nw": 13,
    "ne": 14,
    "sw": 16,
    "se": 17,
    "top": 12,
    "bottom": 15,
    "left": 10,
    "right": 11,
    "top-left": 13,
    "top-right": 14,
    "bottom-left": 16,
    "bottom-right": 17,
    "move": 2,
}


def _windows_native_drag(window: webview.Window, ht_code: int) -> bool:
    """Dispatches native Windows WM_NCLBUTTONDOWN message via ctypes."""
    import deskai.bridge.api as _api

    active_sys = getattr(_api, "sys", sys)
    if active_sys.platform != "win32":
        return False
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        user32 = windll.user32
        hwnd = getattr(window, "native", None)
        if not isinstance(hwnd, int):
            raw_title = getattr(window, "title", None)
            title = raw_title if isinstance(raw_title, str) and raw_title else "DeskAI"
            hwnd = user32.FindWindowW(None, title)
        if isinstance(hwnd, int) and hwnd > 0:
            WM_NCLBUTTONDOWN = 0x00A1
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, ht_code, 0)
            return True
    except Exception as e:
        logger.debug("Windows native drag error: %s", e)
    return False


class WindowChromeBridge(BaseBridgeModule):
    """Bridge methods for window movement, sizing, and chrome controls."""

    def drag_window(self, timestamp: float | None = None) -> bool:
        """Initiates native window move drag across Windows and Linux (Wayland/X11)."""
        if not self._is_origin_allowed():
            return False

        if sys.platform == "win32":
            return _windows_native_drag(self._window, 2)

        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_move_drag"):
            try:
                import gi

                try:
                    gi.require_version("Gdk", "3.0")
                except ValueError:
                    pass
                from gi.repository import GLib, Gdk

                def _do_drag():
                    try:
                        display = Gdk.Display.get_default()
                        if display:
                            seat = display.get_default_seat()
                            if seat:
                                pointer = seat.get_pointer()
                                if pointer:
                                    _, x, y = pointer.get_position()
                                    native.begin_move_drag(1, int(x), int(y), Gdk.CURRENT_TIME)
                    except Exception as e:
                        logger.debug("Native drag error: %s", e)

                GLib.idle_add(_do_drag)
                return True
            except Exception as e:
                logger.debug("Bridge drag error: %s", e)
                return False
        return False

    def resize_window(self, edge: str, timestamp: float | None = None) -> bool:
        """Initiates native window resize drag across Windows and Linux (Wayland/X11)."""
        if not self._is_origin_allowed():
            return False

        if edge not in RESIZE_DIRECTIONS:
            raise ValueError(f"Invalid resize direction: {edge}")

        if sys.platform == "win32":
            ht_code = RESIZE_DIRECTIONS[edge]
            return _windows_native_drag(self._window, ht_code)

        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_resize_drag"):
            try:
                import gi

                try:
                    gi.require_version("Gdk", "3.0")
                except ValueError:
                    pass
                from gi.repository import GLib, Gdk

                if hasattr(native, "is_maximized") and native.is_maximized():
                    return False

                edge_map = {
                    "top": Gdk.WindowEdge.NORTH,
                    "n": Gdk.WindowEdge.NORTH,
                    "bottom": Gdk.WindowEdge.SOUTH,
                    "s": Gdk.WindowEdge.SOUTH,
                    "left": Gdk.WindowEdge.WEST,
                    "w": Gdk.WindowEdge.WEST,
                    "right": Gdk.WindowEdge.EAST,
                    "e": Gdk.WindowEdge.EAST,
                    "top-left": Gdk.WindowEdge.NORTH_WEST,
                    "nw": Gdk.WindowEdge.NORTH_WEST,
                    "top-right": Gdk.WindowEdge.NORTH_EAST,
                    "ne": Gdk.WindowEdge.NORTH_EAST,
                    "bottom-left": Gdk.WindowEdge.SOUTH_WEST,
                    "sw": Gdk.WindowEdge.SOUTH_WEST,
                    "bottom-right": Gdk.WindowEdge.SOUTH_EAST,
                    "se": Gdk.WindowEdge.SOUTH_EAST,
                }
                edge_enum = edge_map.get(edge)
                if edge_enum is None:
                    return False

                def _do_resize():
                    try:
                        display = Gdk.Display.get_default()
                        if display:
                            seat = display.get_default_seat()
                            if seat:
                                pointer = seat.get_pointer()
                                if pointer:
                                    _, x, y = pointer.get_position()
                                    native.begin_resize_drag(edge_enum, 1, int(x), int(y), Gdk.CURRENT_TIME)
                    except Exception as e:
                        logger.debug("Native resize error: %s", e)

                GLib.idle_add(_do_resize)
                return True
            except Exception as e:
                logger.debug("Bridge resize error: %s", e)
                return False
        return False

    def resize_window_absolute(self, width: int, height: int) -> dict:
        """Directly resizes native window frame to specified dimensions within sane bounds (200..10000)."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if type(width) is not int or type(height) is not int or isinstance(width, bool) or isinstance(height, bool):
            return {"status": "error", "message": "width and height must be integers"}
        if not (200 <= width <= 10000) or not (200 <= height <= 10000):
            return {"status": "error", "message": "width and height must be in range 200..10000"}
        win = self._window
        if not win:
            return {"status": "error", "message": "Window unavailable"}
        try:
            win.resize(width, height)
            return {"status": "ok", "width": width, "height": height}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_control(self, action: str, direction: str | None = None, timestamp: float | None = None) -> bool:
        """Handles native window frame buttons and frameless drag/resize actions."""
        if not self._is_origin_allowed():
            return False
        win = self._window
        if not win:
            return False

        valid_actions = {
            "minimize",
            "maximize",
            "close",
            "close_request",
            "drag_start",
            "resize_start",
            "resize_absolute",
        }
        if action not in valid_actions:
            raise ValueError(f"Unknown window control action: {action}")

        if action == "minimize":
            win.minimize()
            return True
        elif action == "maximize":
            # Toggle maximize/restore
            native = getattr(win, "native", None)
            if native and hasattr(native, "is_maximized"):
                try:
                    from gi.repository import GLib

                    if native.is_maximized():
                        GLib.idle_add(native.unmaximize)
                    else:
                        GLib.idle_add(native.maximize)
                    return True
                except Exception:
                    pass
            win.toggle_fullscreen()
            return True
        elif action == "close":
            if self._manager.lifecycle.confirm_exit():
                self._manager.lifecycle._exit_confirmed = True
                win.destroy()
                return True
            return False
        elif action == "close_request":
            if not self._manager.lifecycle.has_dirty_tabs and not self._manager.lifecycle.has_running_terminal:
                self._manager.lifecycle._exit_confirmed = True
                win.destroy()
                return True
            return False
        elif action == "drag_start":
            return self.drag_window(timestamp=timestamp)
        elif action == "resize_start":
            if not direction or direction not in RESIZE_DIRECTIONS:
                raise ValueError(f"Invalid resize direction: {direction}")
            return self.resize_window(direction, timestamp=timestamp)
        return False

    def set_dirty_status(self, is_dirty: bool):
        """Pushed by frontend whenever active editor buffers change."""
        if not self._is_origin_allowed():
            return
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)
