# Layer 1 Technology LLD: PyWebView Desktop Wrapper & Native Bridge Implementation

Yeh document **DeskAI** ke **Layer 1 (Presentation & Native Shell)** mein use hone wali **PyWebView** library aur desktop supervisor server ki mukammal **Low-Level Design (LLD)** specifications, Python class models, method signatures, race-free socket handover, endpoint-level WebSocket guard, single-use token redemption, aur path sandboxing ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Scope

PyWebView aur iska underlying local server application ka **native shell aur OS boundary supervisor** hai:

### Low-Level Responsibilities:
1. **Container Management:** WebKitGTK (Linux) / WebView2 (Windows) window initialize karna without double-prompt issues.
2. **Race-Free Socket Handover:** Python listening socket bind kar ke direct Uvicorn server ko handover karna.
3. **Endpoint-Level WebSocket Guard:** Middleware ke bajaye direct `/ws` route ke andar `accept()` se pehle Host, Origin, aur Cookie verification.
4. **Single-Use Token Redemption:** Initial launch token ko first request par invalidate kar ke unique `session_id` cookie issue karna.
5. **Fail-Closed Workspace Sandbox:** Jab tak user explicitly folder select na kare, workspace root `None` rehta hai aur tamam operations blocked rehte hain.
6. **Cross-Origin & Navigation Defense:** Link clicks aur drag/drop events ko WebKit window se bahar default browser par route karna.

---

## 2. Directory & Module Architecture

```text
src/deskai/
├── bridge/
│   ├── __init__.py               # Package exports
│   ├── window.py                 # WindowManager class (GTK/WebView2 setup & flags)
│   ├── api.py                    # DesktopBridgeAPI (Private path guard & native dialogs)
│   └── lifecycle.py              # WindowLifecycleHandler (Dirty flag & clean exit)
├── server/
│   ├── __init__.py
│   ├── app.py                    # FastAPI application, static mounting & routes
│   ├── supervisor.py             # DesktopServer (Socket handover, startup & shutdown)
│   └── security.py               # Session store, single-use token & WebSocket guard
└── utils/
    ├── net.py                    # Socket allocator & host verifier
    └── platform.py               # Cross-platform guards (Linux/NVIDIA checks)
```

---

## 3. Class Specifications & Method Signatures

### 3.1 `WindowManager` Class (`bridge/window.py`)

```python
import os
import sys
import socket
import secrets
from typing import Optional
import webview
from pydantic import BaseModel
from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.lifecycle import WindowLifecycleHandler
from deskai.server.supervisor import DesktopServer

class WindowConfig(BaseModel):
    title: str = "DeskAI Studio"
    width: int = 1440
    height: int = 900
    min_width: int = 1024
    min_height: int = 680
    resizable: bool = True
    frameless: bool = False             # Native OS window decorations enabled
    background_color: str = "#0a0c12"
    confirm_close: bool = False        # Controlled via JS dirty state handler
    text_select: bool = True

class WindowManager:
    _instance: Optional['WindowManager'] = None
    window: Optional[webview.Window] = None

    def __init__(self, config: WindowConfig):
        self.config = config
        self.launch_token = secrets.token_urlsafe(32)
        
        # 1. Race-Free Listening Socket Allocation
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.bind(('127.0.0.1', 0))
        self.listen_socket.listen(128)
        self.port = self.listen_socket.getsockname()[1]
        
        # 2. Server & Bridge Initialization
        self.api = DesktopBridgeAPI(self)
        self.server = DesktopServer(self.listen_socket, self.port, self.launch_token)
        self.lifecycle = WindowLifecycleHandler(self)

    def initialize_window(self) -> webview.Window:
        # Start server background thread with bound socket
        self.server.start()

        # Token-to-Cookie Redemption Entrypoint
        target_url = f"http://127.0.0.1:{self.port}/auth/redeem?token={self.launch_token}"
        self.window = webview.create_window(
            title=self.config.title,
            url=target_url,
            js_api=self.api,
            width=self.config.width,
            height=self.config.height,
            min_size=(self.config.min_width, self.config.min_height),
            resizable=self.config.resizable,
            frameless=self.config.frameless,
            background_color=self.config.background_color,
            confirm_close=self.config.confirm_close,
            text_select=self.config.text_select
        )
        self.lifecycle.attach_hooks(self.window)
        return self.window

    def start_loop(self, debug: bool = False) -> None:
        if sys.platform.startswith("linux"):
            os.environ.setdefault("GDK_BACKEND", "x11,wayland")
            if os.path.exists("/proc/driver/nvidia") and os.getenv("DESKAI_DISABLE_DMABUF", "1") == "1":
                os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
            webview.start(gui="gtk", debug=debug)
        elif sys.platform.startswith("win"):
            webview.start(gui="edgechromium", debug=debug)
        else:
            webview.start(debug=debug)
```

---

### 3.2 `DesktopBridgeAPI` Class (`bridge/api.py`)

Path checking methods ko private (`_`) banaya gaya hai taake JS context mein expose na hon:

```python
import os
import sys
import webbrowser
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import webview

class ErrorCode:
    ERR_SANDBOX_VIOLATION = "ERR_SANDBOX_VIOLATION"
    ERR_NO_WORKSPACE = "ERR_NO_WORKSPACE"
    ERR_DIALOG_CANCELLED = "ERR_DIALOG_CANCELLED"
    ERR_FILE_NOT_FOUND = "ERR_FILE_NOT_FOUND"
    ERR_WIN_CONTROL_FAILED = "ERR_WIN_CONTROL_FAILED"
    ERR_INVALID_URL = "ERR_INVALID_URL"
    ERR_INTERNAL = "ERR_INTERNAL"

class BridgeResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager'):
        self._manager = manager
        # Fail-closed: None until user explicitly selects a directory
        self._workspace_root: Optional[str] = None

    def _is_disallowed_root(self, path: str) -> bool:
        """Blocks overly broad root folders like '/', '/home', 'C:\\'."""
        normalized = os.path.realpath(path)
        if normalized in ["/", "/home", "/root"]:
            return True
        if sys.platform.startswith("win") and len(normalized.split(os.sep)) <= 2:
            return True
        return False

    def _assert_within_workspace(self, path: str) -> str:
        """Private sandbox validator. Verifies path is strictly inside workspace."""
        if not self._workspace_root:
            raise PermissionError("No workspace folder is currently open.")

        real_target = os.path.realpath(path)
        real_root = os.path.realpath(self._workspace_root)
        
        if sys.platform.startswith("win"):
            real_target = os.path.normcase(real_target)
            real_root = os.path.normcase(real_root)

        try:
            common = os.path.commonpath([real_target, real_root])
            if common != real_root:
                raise PermissionError(f"Access denied: {path} is outside workspace boundary.")
        except ValueError:
            raise PermissionError(f"Cross-drive or invalid path access: {path}")

        return real_target

    def open_directory_dialog(self, title: str = "Select Project Folder") -> Dict[str, Any]:
        """Native Folder Picker dialog open karta hai aur active workspace set karta hai."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                directory=True
            )
            selected_path = result[0] if result and len(result) > 0 else None
            if selected_path:
                if self._is_disallowed_root(selected_path):
                    return BridgeResponse(
                        success=False, 
                        error="Cannot select system root as workspace.", 
                        error_code=ErrorCode.ERR_SANDBOX_VIOLATION
                    ).dict()
                self._workspace_root = os.path.realpath(selected_path)
            return BridgeResponse(success=True, data={"path": selected_path}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def open_file_dialog(
        self, 
        file_types: List[str] = ("Supported Files (*.py;*.js;*.html;*.css;*.json;*.md)", "All Files (*.*)"),
        allow_multiple: bool = False
    ) -> Dict[str, Any]:
        """Native File Picker dialog with sandbox validation."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=allow_multiple,
                directory=False,
                file_types=file_types
            )
            files = list(result) if result else []
            validated = []
            for f in files:
                try:
                    validated.append(self._assert_within_workspace(f))
                except PermissionError as pe:
                    return BridgeResponse(success=False, error=str(pe), error_code=ErrorCode.ERR_SANDBOX_VIOLATION).dict()

            return BridgeResponse(success=True, data={"files": validated}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        try:
            self._manager.window.set_clipboard(text)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def open_external_url(self, url: str) -> Dict[str, Any]:
        """External web links ko OS ke default browser mein safely open karta hai."""
        try:
            if not url.startswith(("http://", "https://", "mailto:")):
                return BridgeResponse(success=False, error="Unsupported scheme", error_code=ErrorCode.ERR_INVALID_URL).dict()
            webbrowser.open(url)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def set_dirty_status(self, is_dirty: bool) -> Dict[str, Any]:
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)
        return BridgeResponse(success=True).dict()

    def control_window(self, action: str) -> Dict[str, Any]:
        win = self._manager.window
        try:
            if action == "minimize":
                win.minimize()
            elif action == "maximize":
                win.maximize()
            elif action == "restore":
                win.restore()
            elif action == "close":
                if self._manager.lifecycle.confirm_exit():
                    win.destroy()
            return BridgeResponse(success=True, data={"action": action}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_WIN_CONTROL_FAILED).dict()
```

---

## 4. Complete Desktop Server & WebSocket Security (`server/supervisor.py`)

FastAPI application, static mounting, single-use token redemption, aur endpoint-level WebSocket guard ka complete implementation:

```python
import secrets
import threading
from pathlib import Path
import socket
from typing import Set
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

class DesktopServer:
    def __init__(self, listen_socket: socket.socket, port: int, initial_token: str):
        self.listen_socket = listen_socket
        self.port = port
        self.launch_token = initial_token
        self.active_sessions: Set[str] = set()
        self.server_thread: Optional[threading.Thread] = None
        self.uvicorn_server: Optional[uvicorn.Server] = None
        
        self.app = FastAPI(docs_url=None, redoc_url=None)
        self._setup_routes()

    def _setup_routes(self):
        static_dir = Path(__file__).resolve().parent.parent / "static"
        
        # 1. HTTP Middleware (Security Headers & Host Verification)
        @self.app.middleware("http")
        async def http_security(request: Request, call_next):
            host = request.headers.get("host", "")
            if host not in [f"127.0.0.1:{self.port}", f"localhost:{self.port}"]:
                return Response("Forbidden: Invalid Host", status_code=status.HTTP_403_FORBIDDEN)

            origin = request.headers.get("origin")
            if origin and origin != f"http://127.0.0.1:{self.port}":
                return Response("Forbidden: Cross-Origin Request Blocked", status_code=status.HTTP_403_FORBIDDEN)

            # Route authentication check
            if not request.url.path.startswith("/auth/redeem"):
                cookie = request.cookies.get("deskai_session")
                if not cookie or cookie not in self.active_sessions:
                    return Response("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

            response = await call_next(request)
            
            # Exact dynamic port CSP & security headers
            csp = (
                "default-src 'self'; "
                f"connect-src 'self' ws://127.0.0.1:{self.port} http://127.0.0.1:{self.port}; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "object-src 'none'; "
                "base-uri 'none'; "
                "form-action 'none';"
            )
            response.headers["Content-Security-Policy"] = csp
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response

        # 2. Single-Use Token Redemption
        @self.app.get("/auth/redeem")
        async def redeem(token: str):
            if not self.launch_token or not secrets.compare_digest(token, self.launch_token):
                raise HTTPException(status_code=403, detail="Invalid or expired token.")

            # Invalidate launch token immediately (Single Use)
            self.launch_token = None

            # Issue distinct session id
            session_id = secrets.token_urlsafe(32)
            self.active_sessions.add(session_id)

            resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
            resp.set_cookie(
                key="deskai_session",
                value=session_id,
                httponly=True,
                samesite="strict",
                path="/"
            )
            return resp

        # 3. Root Page & Static Files
        @self.app.get("/")
        async def serve_index():
            return FileResponse(static_dir / "index.html")

        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        # 4. HARDENED WebSocket Endpoint (Guarded BEFORE accept())
        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            # A. Verify Host Header
            host = ws.headers.get("host", "")
            if host not in [f"127.0.0.1:{self.port}", f"localhost:{self.port}"]:
                await ws.close(code=1008, reason="Invalid Host")
                return

            # B. Verify Origin Header (Strict Match - Null Not Allowed)
            origin = ws.headers.get("origin")
            if origin != f"http://127.0.0.1:{self.port}":
                await ws.close(code=1008, reason="Cross-Origin WebSocket Denied")
                return

            # C. Verify Session Cookie
            cookie = ws.cookies.get("deskai_session")
            if not cookie or cookie not in self.active_sessions:
                await ws.close(code=1008, reason="Unauthorized Session")
                return

            # All checks passed -> Accept connection
            await ws.accept()
            try:
                while True:
                    data = await ws.receive_json()
                    # Route actions (e.g. uec.action, telemetry request)
                    await ws.send_json({"type": "ack", "seq": data.get("seq", 0)})
            except WebSocketDisconnect:
                pass

    def start(self):
        config = uvicorn.Config(
            app=self.app,
            log_config=None,
            access_log=False  # Do not print query tokens to terminal
        )
        self.uvicorn_server = uvicorn.Server(config)
        self.server_thread = threading.Thread(
            target=self.uvicorn_server.run,
            kwargs={"sockets": [self.listen_socket]},
            daemon=True
        )
        self.server_thread.start()

    def stop(self):
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
```
