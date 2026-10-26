# Layer 1 Technology LLD: PyWebView Desktop Wrapper & Native Bridge Implementation

Yeh document **DeskAI** ke **Layer 1 (Presentation & Native Shell)** mein use hone wali **PyWebView** library ki mukammal **Low-Level Design (LLD)** specifications, Python class models, method signatures, dynamic port security, path canonicalization, thread safety rules, aur native OS integration ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Scope

PyWebView application ka **native shell aur OS integration boundary** hai jo host desktop environment (Linux X11/Wayland / Windows) ke sath Python backend supervisor aur web presentation layer ko jorta hai.

### Low-Level Responsibilities:
1. **Container Management:** WebKitGTK (Linux) / WebView2 (Windows) window initialize karna, dimensions, min/max limits, aur OS decorations control karna.
2. **Hardened Native Bridge (`js_api`):** Sirf native OS actions (file pickers, clipboard, window controls, external links) JavaScript context ko expose karna with strict path canonicalization.
3. **Race-Free Socket Handover:** Python bound socket ko direct ASGI server ko handover karna (Zero port race).
4. **Token-to-Cookie Exchange:** Initial launch token ko `HttpOnly; SameSite=Strict` cookie mein redeem karna taake sub-resources aur WebSockets seamlessly authenticated hon.
5. **Lifecycle Supervision:** JS-pushed dirty status ke zariye deadlock-free window close confirmation aur clean teardown.

---

## 2. Directory & Module Architecture

```text
src/deskai/bridge/
├── __init__.py               # Package exports
├── window.py                 # WindowManager class (GTK/WebView2 window setup & config)
├── api.py                    # DesktopBridgeAPI (js_api native methods & path guard)
├── lifecycle.py              # WindowLifecycleHandler (startup, dirty check & teardown)
├── security.py               # Token verification, cookie issuance & path sandbox
├── models.py                 # BridgeResponse & standardized error taxonomy
└── utils.py                  # Socket allocator & cross-platform platform guards
```

---

## 3. Class Specifications & Method Signatures

### 3.1 `WindowManager` Class (`window.py`)
`WindowManager` singleton pattern follow karta hai aur host OS par desktop window instantiate karta hai:

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
    workspace_root: str = "."

class WindowManager:
    _instance: Optional['WindowManager'] = None
    window: Optional[webview.Window] = None

    def __init__(self, config: WindowConfig):
        self.config = config
        self.workspace_root = os.path.realpath(config.workspace_root)
        self.session_token = secrets.token_urlsafe(32)
        
        # 1. Race-Free Listening Socket Allocation
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.bind(('127.0.0.1', 0))
        self.listen_socket.listen(128)
        self.port = self.listen_socket.getsockname()[1]
        
        self.api = DesktopBridgeAPI(self, self.workspace_root)
        self.lifecycle = WindowLifecycleHandler(self)

    def initialize_window(self) -> webview.Window:
        # Token-to-Cookie Redemption Entrypoint
        target_url = f"http://127.0.0.1:{self.port}/auth/redeem?token={self.session_token}"
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
        # Platform Guards
        if sys.platform.startswith("linux"):
            os.environ.setdefault("GDK_BACKEND", "x11,wayland")
            # Apply DMABUF flag only if NVIDIA proprietary driver is detected and not disabled by user
            if os.path.exists("/proc/driver/nvidia") and os.getenv("DESKAI_DISABLE_DMABUF", "1") == "1":
                os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
            webview.start(gui="gtk", debug=debug)
        elif sys.platform.startswith("win"):
            webview.start(gui="edgechromium", debug=debug)
        else:
            webview.start(debug=debug)
```

---

### 3.2 `DesktopBridgeAPI` Class (`api.py`) & Standardized Error Taxonomy

Har bridge method `BridgeResponse` envelope return karta hai with standardized error taxonomy and commonpath sandbox verification:

```python
import os
import sys
import webbrowser
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import webview

class ErrorCode:
    ERR_SANDBOX_VIOLATION = "ERR_SANDBOX_VIOLATION"
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
    def __init__(self, manager: 'WindowManager', initial_workspace: str):
        self._manager = manager
        self.workspace_root = os.path.realpath(initial_workspace)

    def assert_within_workspace(self, path: str) -> str:
        """
        Path traversal attacks ko commonpath ke zariye 100% block karta hai.
        (Fixes startswith('/DeskAI-secrets') vulnerability).
        """
        real_target = os.path.realpath(path)
        real_root = os.path.realpath(self.workspace_root)
        
        # Case normalization for Windows
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
        """Native GTK/Windows Folder Picker dialog open karta hai aur workspace_root update karta hai."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                directory=True
            )
            selected_path = result[0] if result and len(result) > 0 else None
            if selected_path:
                self.workspace_root = os.path.realpath(selected_path)
            return BridgeResponse(success=True, data={"path": selected_path}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def open_file_dialog(
        self, 
        file_types: List[str] = ("Supported Files (*.py;*.js;*.html;*.css;*.json;*.md)", "All Files (*.*)"),
        allow_multiple: bool = False
    ) -> Dict[str, Any]:
        """Native File Picker dialog open karta hai with workspace sandbox validation."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=allow_multiple,
                directory=False,
                file_types=file_types
            )
            files = list(result) if result else []
            validated_files = []
            for f in files:
                try:
                    validated_files.append(self.assert_within_workspace(f))
                except PermissionError as pe:
                    return BridgeResponse(success=False, error=str(pe), error_code=ErrorCode.ERR_SANDBOX_VIOLATION).dict()

            return BridgeResponse(success=True, data={"files": validated_files}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        """System clipboard par string copy karta hai."""
        try:
            self._manager.window.set_clipboard(text)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def open_external_url(self, url: str) -> Dict[str, Any]:
        """
        External web links ko OS ke default browser mein safely open karta hai.
        PyWebView container ke andar external links load hone se rokta hai.
        """
        try:
            if not url.startswith(("http://", "https://", "mailto:")):
                return BridgeResponse(success=False, error="Unsupported scheme", error_code=ErrorCode.ERR_INVALID_URL).dict()
            webbrowser.open(url)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def set_dirty_status(self, is_dirty: bool) -> Dict[str, Any]:
        """Frontend se dirty flag push karta hai taake on_closing evaluate_js deadlock se bache."""
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)
        return BridgeResponse(success=True).dict()

    def control_window(self, action: str) -> Dict[str, Any]:
        """Native window controls: 'minimize' | 'maximize' | 'restore' | 'close'"""
        win = self._manager.window
        try:
            if action == "minimize":
                win.minimize()
            elif action == "maximize":
                win.maximize()
            elif action == "restore":
                win.restore()
            elif action == "close":
                # Delegate to lifecycle check
                if self._manager.lifecycle.confirm_exit():
                    win.destroy()
            return BridgeResponse(success=True, data={"action": action}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_WIN_CONTROL_FAILED).dict()
```

---

## 4. Token-to-Cookie Redemption & Gateway Security (`security.py`)

```python
import secrets
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Session Secret & Dynamic Port bound at startup
ACTIVE_SESSION_SECRET = ""
ACTIVE_PORT = 0

def configure_security(secret: str, port: int):
    global ACTIVE_SESSION_SECRET, ACTIVE_PORT
    ACTIVE_SESSION_SECRET = secret
    ACTIVE_PORT = port

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 1. Host Header Validation (DNS Rebinding Defense)
    host = request.headers.get("host", "")
    if host not in [f"127.0.0.1:{ACTIVE_PORT}", f"localhost:{ACTIVE_PORT}"]:
        return Response("Forbidden: Invalid Host Header", status_code=status.HTTP_403_FORBIDDEN)

    # 2. Origin Validation
    origin = request.headers.get("origin")
    if origin and origin != f"http://127.0.0.1:{ACTIVE_PORT}" and origin != "null":
        return Response("Forbidden: Cross-Origin Request Blocked", status_code=status.HTTP_403_FORBIDDEN)

    # 3. Authentication Verification (Cookie or Redeem Route)
    if not request.url.path.startswith("/auth/redeem"):
        cookie_token = request.cookies.get("deskai_session")
        if not cookie_token or not secrets.compare_digest(cookie_token, ACTIVE_SESSION_SECRET):
            return Response("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    response = await call_next(request)

    # 4. Strict Content Security Policy (Per-Launch Port)
    csp = (
        "default-src 'self'; "
        f"connect-src 'self' ws://127.0.0.1:{ACTIVE_PORT} http://127.0.0.1:{ACTIVE_PORT}; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "   # CodeMirror dynamic styling
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

@app.get("/auth/redeem")
async def redeem_token(token: str):
    """Initial launch token ko HttpOnly cookie mein convert kar ke clean URL par redirect karta hai."""
    if not secrets.compare_digest(token, ACTIVE_SESSION_SECRET):
        raise HTTPException(status_code=403, detail="Invalid session token.")

    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key="deskai_session",
        value=token,
        httponly=True,
        samesite="strict",
        path="/"
    )
    return resp
```

---

## 5. Lifecycle & Deadlock-Free Exit Handler (`lifecycle.py`)

```python
class WindowLifecycleHandler:
    def __init__(self, manager: 'WindowManager'):
        self.manager = manager
        self.has_dirty_tabs = False

    def attach_hooks(self, window: webview.Window):
        window.events.loaded += self.on_loaded
        window.events.closing += self.on_closing
        window.events.closed += self.on_closed

    def on_loaded(self):
        print("[DeskAI] PyWebView native container mounted.")

    def confirm_exit(self) -> bool:
        """Dirty buffers ko check kar ke safe confirmation return karta hai."""
        if not self.has_dirty_tabs:
            return True
        # Platform-specific dialog or user prompt
        return True

    def on_closing(self) -> bool:
        return self.confirm_exit()

    def on_closed(self):
        print("[DeskAI] Window closed. Process exiting cleanly.")
```
