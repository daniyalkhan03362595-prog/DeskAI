"""
DesktopBridgeAPI Implementation:
Exposed to JavaScript via window.pywebview.api.
Handles native dialogs, external URL dispatch, window controls, and path sandboxing.
"""
import os
import webbrowser
from typing import TYPE_CHECKING
import webview

from deskai.utils.path import is_safe_workspace_path, canonicalize_path

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager'):
        self._manager = manager
        self.workspace_root: str | None = None

    @property
    def _window(self) -> webview.Window:
        return self._manager.window

    def select_folder(self) -> dict:
        """Opens native OS folder selection dialog."""
        selected = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if selected and len(selected) > 0:
            folder_path = canonicalize_path(selected[0])
            self.workspace_root = folder_path
            return {"status": "ok", "path": folder_path, "name": os.path.basename(folder_path)}
        return {"status": "cancelled", "path": None}

    def select_file(self) -> dict:
        """Opens native OS file selection dialog."""
        selected = self._window.create_file_dialog(webview.OPEN_DIALOG)
        if selected and len(selected) > 0:
            file_path = canonicalize_path(selected[0])
            return {"status": "ok", "path": file_path, "name": os.path.basename(file_path)}
        return {"status": "cancelled", "path": None}

    def save_file_dialog(self, default_name: str = "untitled.txt") -> dict:
        """Opens native OS file save dialog."""
        selected = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
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

    def window_control(self, action: str) -> bool:
        """Handles native window frame buttons."""
        if action == "minimize":
            self._window.minimize()
            return True
        elif action == "maximize":
            # Toggle maximize/restore
            self._window.toggle_fullscreen()
            return True
        elif action == "close":
            self._window.destroy()
            return True
        return False

    def set_dirty_status(self, is_dirty: bool):
        """Pushed by frontend whenever active editor buffers change."""
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)

    def _is_safe_path(self, target_path: str) -> bool:
        """Internal sandbox helper."""
        return is_safe_workspace_path(target_path, self.workspace_root)
