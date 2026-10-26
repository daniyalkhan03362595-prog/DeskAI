"""
DesktopBridgeAPI Implementation:
Exposed to JavaScript via window.pywebview.api.
Handles native dialogs, external URL dispatch, window controls, and path sandboxing.
"""
import os
import sys
import webbrowser
from typing import TYPE_CHECKING
import webview

from deskai.utils.path import is_safe_workspace_path, canonicalize_path, is_disallowed_workspace_root

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


# Support both pywebview 6.x (webview.FileDialog) and 5.x (webview.FOLDER_DIALOG)
def _get_dialog_type(name: str, fallback_attr: str, default_code: int):
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog and hasattr(file_dialog, name):
        return getattr(file_dialog, name)
    return getattr(webview, fallback_attr, default_code)


DIALOG_FOLDER = _get_dialog_type("FOLDER", "FOLDER_DIALOG", 20)
DIALOG_OPEN = _get_dialog_type("OPEN", "OPEN_DIALOG", 10)
DIALOG_SAVE = _get_dialog_type("SAVE", "SAVE_DIALOG", 30)

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
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = getattr(window, "native", None)
        if not hwnd or not isinstance(hwnd, int):
            title = getattr(window, "title", "DeskAI")
            hwnd = user32.FindWindowW(None, title)
        if hwnd:
            WM_NCLBUTTONDOWN = 0x00A1
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, ht_code, 0)
            return True
    except Exception as e:
        print(f"[DeskAI] Windows native drag error: {e}")
    return False


class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager'):
        self._manager = manager
        self.workspace_root: str | None = None

    @property
    def _window(self) -> webview.Window:
        return self._manager.window

    def _is_origin_allowed(self) -> bool:
        """Ensures caller originates strictly from the local application origin."""
        if not self._window:
            return False
        port = getattr(getattr(self._manager, "server", None), "port", None)
        if port is None:
            return False
        get_url = getattr(self._window, "get_current_url", None)
        if not get_url:
            return False
        current_url = get_url() or ""
        expected_origin = f"http://127.0.0.1:{port}"
        if current_url.startswith(expected_origin):
            suffix = current_url[len(expected_origin):]
            if not suffix or suffix.startswith(("/", "?", "#")):
                return True
        return False

    def select_folder(self) -> dict:
        """Opens native OS folder selection dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_FOLDER)
        if selected and len(selected) > 0:
            folder_path = canonicalize_path(selected[0])
            if is_disallowed_workspace_root(folder_path):
                return {"status": "error", "message": "Disallowed system directory", "path": None}
            self.workspace_root = folder_path
            return {"status": "ok", "path": folder_path, "name": os.path.basename(folder_path)}
        return {"status": "cancelled", "path": None}

    def select_file(self) -> dict:
        """Opens native OS file selection dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_OPEN)
        if selected and len(selected) > 0:
            file_path = canonicalize_path(selected[0])
            return {"status": "ok", "path": file_path, "name": os.path.basename(file_path)}
        return {"status": "cancelled", "path": None}

    def save_file_dialog(self, default_name: str = "untitled.txt") -> dict:
        """Opens native OS file save dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(
            DIALOG_SAVE,
            save_filename=default_name
        )
        if selected:
            return {"status": "ok", "path": canonicalize_path(selected)}
        return {"status": "cancelled", "path": None}

    def open_external_url(self, url: str) -> bool:
        """
        Dispatches web URLs to the user's default OS browser.
        Blocks javascript: or file: URLs to prevent sandbox breakout.
        """
        if not self._is_origin_allowed():
            return False
        if not url:
            return False
        clean_url = url.strip()
        if clean_url.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(clean_url)
            return True
        return False

    def drag_window(self, timestamp: float | None = None) -> bool:
        """Initiates native window move drag across Windows and Linux (Wayland/X11)."""
        if not self._is_origin_allowed():
            return False

        if sys.platform == "win32":
            return _windows_native_drag(self._window, 2)

        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_move_drag"):
            try:
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
                        print(f"[DeskAI] Native drag error: {e}")
                GLib.idle_add(_do_drag)
                return True
            except Exception as e:
                print(f"[DeskAI] Bridge drag error: {e}")
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
                        print(f"[DeskAI] Native resize error: {e}")
                GLib.idle_add(_do_resize)
                return True
            except Exception as e:
                print(f"[DeskAI] Bridge resize error: {e}")
                return False
        return False

    def window_control(
        self,
        action: str,
        direction: str | None = None,
        timestamp: float | None = None
    ) -> bool:
        """Handles native window frame buttons and frameless drag/resize actions."""
        if not self._is_origin_allowed():
            return False

        valid_actions = {
            "minimize",
            "maximize",
            "close",
            "close_request",
            "drag_start",
            "resize_start"
        }
        if action not in valid_actions:
            raise ValueError(f"Unknown window control action: {action}")

        if action == "minimize":
            self._window.minimize()
            return True
        elif action == "maximize":
            # Toggle maximize/restore
            native = getattr(self._window, "native", None)
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
            self._window.toggle_fullscreen()
            return True
        elif action == "close":
            if self._manager.lifecycle.confirm_exit():
                self._manager.lifecycle._exit_confirmed = True
                self._window.destroy()
                return True
            return False
        elif action == "close_request":
            if not self._manager.lifecycle.has_dirty_tabs:
                self._manager.lifecycle._exit_confirmed = True
                self._window.destroy()
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

    def _is_safe_path(self, target_path: str) -> bool:
        """Internal sandbox helper."""
        return is_safe_workspace_path(target_path, self.workspace_root)
