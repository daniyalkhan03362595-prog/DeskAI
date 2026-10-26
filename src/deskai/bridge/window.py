"""
WindowManager Implementation:
Native PyWebView window configuration, flags, and server lifecycle bootstrapping.
"""
import sys
import webview

from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.lifecycle import WindowLifecycleHandler
from deskai.server.supervisor import DesktopServer


class WindowManager:
    def __init__(self, title: str = "DeskAI Studio", width: int = 1280, height: int = 800):
        self.title = title
        self.width = width
        self.height = height

        self.server = DesktopServer()
        self.api = DesktopBridgeAPI(self)
        self.lifecycle = WindowLifecycleHandler(self)
        self.window: webview.Window | None = None

    def initialize_window(self) -> webview.Window:
        """Starts backend server and creates PyWebView window with redeem URL."""
        # 1. Start background server with bound loopback socket
        self.server.start()

        # 2. Token-to-Cookie Redemption Entrypoint
        initial_url = f"http://127.0.0.1:{self.server.port}/auth/redeem?token={self.server.launch_token}"

        # 3. Create native window
        self.window = webview.create_window(
            title=self.title,
            url=initial_url,
            js_api=self.api,
            width=self.width,
            height=self.height,
            min_size=(900, 600),
            frameless=True,
            easy_drag=False,
            confirm_close=False,  # Managed by WindowLifecycleHandler
            background_color="#0a0c12"
        )

        # 4. Attach lifecycle listeners
        self.lifecycle.attach_hooks(self.window)
        return self.window

    def run(self, debug: bool = False):
        """Starts GUI event loop."""
        self.initialize_window()

        # Select native GUI backend based on platform
        gui_backend = None
        if sys.platform.startswith("linux"):
            gui_backend = "gtk"

        try:
            webview.start(debug=debug, gui=gui_backend)
        finally:
            self.server.stop()
