"""
DesktopBridgeAPI Facade:
Thin facade exposed to JavaScript via window.pywebview.api.
Composes focused bridge modules: window_chrome, workspace_fs, ports, git, telemetry, and terminal.
"""

import sys  # noqa: F401 (retained on API namespace for backward-compatible test patching)
from typing import TYPE_CHECKING

from deskai.bridge.base import BaseBridgeModule
from deskai.bridge.diagnostics import DiagnosticsBridge
from deskai.bridge.git import GitBridge
from deskai.bridge.ports import (
    PortsBridge,
    _LOOPBACK_HOSTS,
    _is_safe_external_url,
    _reachable_host,
)
from deskai.bridge.telemetry import TelemetryBridge
from deskai.bridge.terminal import TerminalBridge
from deskai.bridge.window_chrome import (
    WindowChromeBridge,
    RESIZE_DIRECTIONS,
    _windows_native_drag,
)
from deskai.bridge.workspace_fs import (
    WorkspaceFSBridge,
    DIALOG_FOLDER,
    DIALOG_OPEN,
    DIALOG_SAVE,
    _get_dialog_type,
)

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


class DesktopBridgeAPI(
    WindowChromeBridge,
    WorkspaceFSBridge,
    PortsBridge,
    GitBridge,
    TelemetryBridge,
    TerminalBridge,
    DiagnosticsBridge,
    BaseBridgeModule,
):
    """
    Composite bridge facade exposed to PyWebView js_api.
    Inherits all capability methods, ensuring pywebview reflection (dir/getattr)
    discovers every method with strict local origin enforcement.
    """

    def __init__(self, manager: "WindowManager"):
        BaseBridgeModule.__init__(self, manager)


__all__ = [
    "DesktopBridgeAPI",
    "DIALOG_FOLDER",
    "DIALOG_OPEN",
    "DIALOG_SAVE",
    "RESIZE_DIRECTIONS",
    "_windows_native_drag",
    "_is_safe_external_url",
    "_reachable_host",
    "_LOOPBACK_HOSTS",
    "_get_dialog_type",
]
