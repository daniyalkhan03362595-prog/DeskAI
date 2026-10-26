"""
Window Lifecycle & Safe Exit Handler.
Tracks unsaved buffers and handles clean server shutdown on exit.
"""
from typing import TYPE_CHECKING
import webview

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


class WindowLifecycleHandler:
    def __init__(self, manager: 'WindowManager'):
        self.manager = manager
        self.has_dirty_tabs: bool = False

    def attach_hooks(self, window: webview.Window):
        window.events.loaded += self.on_loaded
        window.events.closing += self.on_closing
        window.events.closed += self.on_closed

    def on_loaded(self):
        print("[DeskAI] PyWebView presentation container initialized.")

    def confirm_exit(self) -> bool:
        """Prompts confirmation if unsaved changes exist."""
        if not self.has_dirty_tabs:
            return True

        if hasattr(self.manager.window, "create_confirmation_dialog"):
            result = self.manager.window.create_confirmation_dialog(
                "Unsaved Changes",
                "You have unsaved changes in your workspace. Are you sure you want to exit?"
            )
            return bool(result)
        return True

    def on_closing(self) -> bool:
        return self.confirm_exit()

    def on_closed(self):
        print("[DeskAI] Window closed. Stopping desktop supervisor server...")
        self.manager.server.stop()
