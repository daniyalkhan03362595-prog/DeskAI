"""
DesktopBridgeAPI Implementation:
Exposed to JavaScript via window.pywebview.api.
Handles native dialogs, external URL dispatch, window controls, and path sandboxing.
"""
import os
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


class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager'):
        self._manager = manager
        self.workspace_root: str | None = None

    @property
    def _window(self) -> webview.Window:
        return self._manager.window

    def select_folder(self) -> dict:
        """Opens native OS folder selection dialog."""
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
        selected = self._window.create_file_dialog(DIALOG_OPEN)
        if selected and len(selected) > 0:
            file_path = canonicalize_path(selected[0])
            return {"status": "ok", "path": file_path, "name": os.path.basename(file_path)}
        return {"status": "cancelled", "path": None}

    def save_file_dialog(self, default_name: str = "untitled.txt") -> dict:
        """Opens native OS file save dialog."""
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
        if not url:
            return False
        clean_url = url.strip()
        if clean_url.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(clean_url)
            return True
        return False

    def drag_window(self) -> bool:
        """Initiates native Wayland/X11 window move drag via GTK begin_move_drag."""
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

    def resize_window(self, edge: str) -> bool:
        """Initiates native Wayland/X11 window resize drag via GTK begin_resize_drag."""
        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_resize_drag"):
            try:
                from gi.repository import GLib, Gdk
                if hasattr(native, "is_maximized") and native.is_maximized():
                    return False

                edge_map = {
                    "top": Gdk.WindowEdge.NORTH,
                    "bottom": Gdk.WindowEdge.SOUTH,
                    "left": Gdk.WindowEdge.WEST,
                    "right": Gdk.WindowEdge.EAST,
                    "top-left": Gdk.WindowEdge.NORTH_WEST,
                    "top-right": Gdk.WindowEdge.NORTH_EAST,
                    "bottom-left": Gdk.WindowEdge.SOUTH_WEST,
                    "bottom-right": Gdk.WindowEdge.SOUTH_EAST,
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

    def window_control(self, action: str) -> bool:
        """Handles native window frame buttons."""
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
                self._window.destroy()
                return True
            return False
        return False

    def set_dirty_status(self, is_dirty: bool):
        """Pushed by frontend whenever active editor buffers change."""
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)

    def _is_safe_path(self, target_path: str) -> bool:
        """Internal sandbox helper."""
        return is_safe_workspace_path(target_path, self.workspace_root)
