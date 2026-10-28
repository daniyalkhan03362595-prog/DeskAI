"""
Base module providing core origin validation and state for DesktopBridgeAPI modules.
"""

import logging
from typing import TYPE_CHECKING
import webview

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager

logger = logging.getLogger(__name__)


class BaseBridgeModule:
    """Provides shared manager, window, and security origin checks."""

    def __init__(self, manager: "WindowManager"):
        self._manager = manager
        self.workspace_root: str | None = None
        self._terminal_confirmed_in_session: bool = False

    @property
    def _window(self) -> webview.Window | None:
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
            suffix = current_url[len(expected_origin) :]
            if not suffix or suffix.startswith(("/", "?", "#")):
                return True
        return False
