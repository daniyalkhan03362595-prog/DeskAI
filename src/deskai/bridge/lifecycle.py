"""
Window Lifecycle & Safe Exit Handler.
Tracks unsaved buffers, ensures origin containment, and handles clean server shutdown on exit.
"""

import sys
from typing import TYPE_CHECKING
import webview

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


class WindowLifecycleHandler:
    def __init__(self, manager: "WindowManager"):
        self.manager = manager
        self.has_dirty_tabs: bool = False
        self._has_running_terminal_override: bool | None = None
        self._exit_confirmed: bool = False
        self._nav_policy_hooked: bool = False
        self._resize_hooked: bool = False

    @property
    def has_running_terminal(self) -> bool:
        """Indicates whether any interactive terminal session is actively running."""
        if self._has_running_terminal_override is not None:
            return self._has_running_terminal_override
        server = getattr(self.manager, "server", None)
        tm = getattr(server, "terminal_manager", None)
        if tm is not None:
            val = getattr(tm, "has_running_terminal", False)
            if isinstance(val, bool):
                return val
        return False

    @has_running_terminal.setter
    def has_running_terminal(self, value: bool):
        self._has_running_terminal_override = value

    def attach_hooks(self, window: webview.Window):
        if hasattr(window.events, "shown"):
            window.events.shown += self.on_shown
        window.events.loaded += self.on_loaded
        window.events.closing += self.on_closing
        window.events.closed += self.on_closed
        self._setup_navigation_policy(window)
        self._setup_linux_frameless_resize(window)

    def on_shown(self):
        """Called when native window is mapped and displayed on screen."""
        window = getattr(self.manager, "window", None)
        if window:
            self._setup_navigation_policy(window)
            self._setup_linux_frameless_resize(window)

    def _setup_linux_frameless_resize(self, window: webview.Window):
        """
        Attaches native GTK button-press listener to WebKit view.
        Initiates Wayland/X11 compositor edge resizing using genuine hardware event timestamps.
        """
        if self._resize_hooked or not sys.platform.startswith("linux"):
            return

        try:
            native_win = getattr(window, "native", None)
            if not native_win:
                return

            from gi.repository import Gdk, WebKit2

            def _on_button_press(wv, event):
                if event.button != 1:
                    return False
                if hasattr(native_win, "is_maximized") and native_win.is_maximized():
                    return False

                alloc = native_win.get_allocation()
                width = alloc.width
                height = alloc.height
                x = event.x
                y = event.y
                margin = 10

                edge = None
                if x <= margin and y <= margin:
                    edge = Gdk.WindowEdge.NORTH_WEST
                elif x >= width - margin and y <= margin:
                    edge = Gdk.WindowEdge.NORTH_EAST
                elif x <= margin and y >= height - margin:
                    edge = Gdk.WindowEdge.SOUTH_WEST
                elif x >= width - margin and y >= height - margin:
                    edge = Gdk.WindowEdge.SOUTH_EAST
                elif x <= margin:
                    edge = Gdk.WindowEdge.WEST
                elif x >= width - margin:
                    edge = Gdk.WindowEdge.EAST
                elif y <= margin:
                    edge = Gdk.WindowEdge.NORTH
                elif y >= height - margin:
                    edge = Gdk.WindowEdge.SOUTH

                if edge is not None:
                    native_win.begin_resize_drag(edge, event.button, int(event.x_root), int(event.y_root), event.time)
                    return True
                return False

            def _hook_wv(widget):
                try:
                    if isinstance(widget, WebKit2.WebView):
                        widget.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                        widget.connect("button-press-event", _on_button_press)
                        return True
                except Exception:
                    pass

                if hasattr(widget, "get_children"):
                    for child in widget.get_children():
                        if _hook_wv(child):
                            return True
                return False

            if _hook_wv(native_win):
                self._resize_hooked = True
                print("[DeskAI] Native GTK frameless resize hook attached.")
        except Exception as e:
            print(f"[DeskAI] Linux native resize setup warning: {e}")

    def _setup_navigation_policy(self, window: webview.Window):
        """Attaches GTK/WebKit decide-policy listener to drop unauthorized navigation."""
        if self._nav_policy_hooked:
            return
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

            if _search_and_hook(native):
                self._nav_policy_hooked = True
        except Exception as e:
            print(f"[DeskAI] Navigation policy setup warning: {e}")

    def on_loaded(self):
        """Validates current URL origin and restores app URL if hijacked."""
        print("[DeskAI] PyWebView presentation container initialized.")
        window = getattr(self.manager, "window", None)
        port = getattr(getattr(self.manager, "server", None), "port", None)
        if window:
            self._setup_navigation_policy(window)
            self._setup_linux_frameless_resize(window)
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
        """Prompts confirmation if unsaved changes exist or a terminal is running."""
        if self._exit_confirmed:
            return True

        reasons = []
        if self.has_dirty_tabs:
            reasons.append("unsaved changes in your workspace")
        if self.has_running_terminal:
            reasons.append("a terminal still running")

        if not reasons:
            self._exit_confirmed = True
            return True

        reason_text = " and ".join(reasons)
        window = getattr(self.manager, "window", None)
        if window and hasattr(window, "create_confirmation_dialog"):
            result = window.create_confirmation_dialog(
                "Confirm Exit", f"You have {reason_text}. Are you sure you want to exit?"
            )
            if result:
                self._exit_confirmed = True
            return bool(result)
        self._exit_confirmed = True
        return True

    def on_closing(self) -> bool:
        if self._exit_confirmed:
            return True
        confirmed = self.confirm_exit()
        if confirmed:
            self._exit_confirmed = True
            return True
        return False

    def on_closed(self):
        print("[DeskAI] Window closed. Stopping desktop supervisor server...")
        self.manager.server.stop()
