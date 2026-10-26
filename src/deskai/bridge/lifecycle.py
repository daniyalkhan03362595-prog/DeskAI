"""
Window Lifecycle & Safe Exit Handler.
Tracks unsaved buffers, ensures origin containment, and handles clean server shutdown on exit.
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
        self._setup_navigation_policy(window)

    def _setup_navigation_policy(self, window: webview.Window):
        """Attaches GTK/WebKit decide-policy listener to drop unauthorized navigation."""
        try:
            native = getattr(window, "native", None)
            port = getattr(getattr(self.manager, "server", None), "port", None)
            if not port or not native:
                return

            expected_prefix = f"http://127.0.0.1:{port}"

            def _search_and_hook(widget):
                try:
                    from gi.repository import WebKit2
                    if isinstance(widget, WebKit2.WebView):
                        def _on_decide_policy(wv, decision, decision_type):
                            if type(decision) is WebKit2.NavigationPolicyDecision:
                                req = decision.get_navigation_action().get_request()
                                uri = req.get_uri() if req else ""
                                if uri and not uri.startswith(expected_prefix):
                                    print(f"[DeskAI] Navigation policy blocked off-origin URI: {uri}")
                                    decision.ignore()
                                    return True
                            return False
                        widget.connect("decide-policy", _on_decide_policy)
                        return True
                except Exception:
                    pass

                if hasattr(widget, "get_children"):
                    for child in widget.get_children():
                        if _search_and_hook(child):
                            return True
                return False

            _search_and_hook(native)
        except Exception as e:
            print(f"[DeskAI] Navigation policy setup warning: {e}")

    def on_loaded(self):
        """Validates current URL origin and restores app URL if hijacked."""
        print("[DeskAI] PyWebView presentation container initialized.")
        window = getattr(self.manager, "window", None)
        port = getattr(getattr(self.manager, "server", None), "port", None)
        if window and port:
            get_url = getattr(window, "get_current_url", None)
            if get_url:
                current_url = get_url() or ""
                expected_origin = f"http://127.0.0.1:{port}"
                is_valid = current_url.startswith(expected_origin) and (
                    len(current_url) == len(expected_origin) or current_url[len(expected_origin)] in ("/", "?", "#")
                )
                if current_url and not is_valid:
                    print(f"[DeskAI] Unauthorized origin navigation detected: {current_url}. Restoring app URL.")
                    load_url = getattr(window, "load_url", None)
                    if load_url:
                        load_url(f"{expected_origin}/")

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
