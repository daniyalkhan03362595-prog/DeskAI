"""
Interactive Terminal Bridge Module.
Handles session initialization, confirmation dialogs, and session teardown.
"""

import logging
import os

from deskai.bridge.base import BaseBridgeModule
from deskai.utils.path import is_disallowed_workspace_root, is_safe_workspace_path

logger = logging.getLogger(__name__)


class TerminalBridge(BaseBridgeModule):
    """Bridge methods for spawning and closing terminal sessions."""

    def terminal_open(
        self,
        cols: int = 80,
        rows: int = 24,
        confirmed: bool = False,
        inline_auth: bool = False,
    ) -> dict:
        """Opens a new interactive host shell in the active workspace."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}

        if type(cols) is not int or type(rows) is not int:
            return {"status": "error", "message": "cols and rows must be integers"}

        if not (10 <= cols <= 500) or not (2 <= rows <= 200):
            return {"status": "error", "message": "cols must be in 10..500 and rows in 2..200"}

        if not self.workspace_root:
            return {"status": "error", "message": "Workspace root not set"}

        if is_disallowed_workspace_root(self.workspace_root):
            return {"status": "error", "message": "Disallowed workspace root"}

        if not is_safe_workspace_path(self.workspace_root, self.workspace_root):
            return {"status": "error", "message": "Unsafe workspace root"}

        if confirmed:
            self._terminal_confirmed_in_session = True

        if not self._terminal_confirmed_in_session:
            ws_name = os.path.basename(self.workspace_root) or self.workspace_root
            if inline_auth:
                return {"status": "auth_required", "workspace": ws_name}

            confirmed_dialog = False
            if self._window and hasattr(self._window, "create_confirmation_dialog"):
                confirmed_dialog = bool(
                    self._window.create_confirmation_dialog(
                        "Terminal Authorization",
                        f"Open a host shell in {ws_name}?",
                    )
                )
            if not confirmed_dialog:
                return {"status": "error", "message": "User declined terminal authorization"}
            self._terminal_confirmed_in_session = True

        server = getattr(self._manager, "server", None)
        tm = getattr(server, "terminal_manager", None)
        if not tm:
            return {"status": "error", "message": "Terminal manager unavailable"}

        try:
            session = tm.create_session(self.workspace_root, cols=cols, rows=rows)
            return {"status": "ok", "session_id": session.session_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def terminal_close(self, session_id: str) -> bool:
        """Closes an active terminal session."""
        if not self._is_origin_allowed():
            return False
        if not isinstance(session_id, str):
            return False
        server = getattr(self._manager, "server", None)
        tm = getattr(server, "terminal_manager", None)
        if not tm:
            return False
        return tm.close_session(session_id)
