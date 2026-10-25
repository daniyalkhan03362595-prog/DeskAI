# Layer 1 Technology LLD: PyWebView Desktop Wrapper & Native Bridge Implementation

Yeh document **DeskAI** ke **Layer 1 (Presentation & Native Shell)** mein use hone wali **PyWebView** library ki mukammal **Low-Level Design (LLD)** specifications, Python class models, method signatures, dynamic port security, path canonicalization, thread safety rules, aur native OS integration ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Scope

PyWebView application ka **native shell aur OS integration boundary** hai jo host desktop environment (Linux X11/Wayland) ke sath Python backend aur web presentation layer ko jorta hai.

### Low-Level Responsibilities:
1. **Window Container Management:** WebKitGTK (Linux) / WebView2 (Windows) window initialize karna, dimensions, min/max limits, aur OS decorations control karna.
2. **Hardened Native Bridge (`js_api`):** Sirf native OS actions (file pickers, clipboard, window state) JavaScript context ko expose karna with strict path canonicalization.
3. **Dynamic Port & Token Injection:** Localhost server ke dynamic port aur per-session secret token ko secure context mein pass karna.
4. **Lifecycle Supervision:** `closing` (dirty buffer verification) aur `closed` (irreversible flush & process kill) hooks ke zariye clean lifecycle maintain karna.

---

## 2. Directory & Module Architecture

Backend ke andar PyWebView wrapper ka module structure:

```text
src/deskai/bridge/
├── __init__.py               # Package exports
├── window.py                 # WindowManager class (GTK window setup & config)
├── api.py                    # DesktopBridgeAPI (js_api native methods)
├── lifecycle.py              # WindowLifecycleHandler (startup, dirty check & teardown)
├── security.py               # Path canonicalization & workspace boundary guard
├── models.py                 # BridgeResponse & standardized error taxonomy
└── utils.py                  # Ephemeral port allocator & NVIDIA Linux workarounds
```

---

## 3. Class Specifications & Method Signatures

### 3.1 `WindowManager` Class (`window.py`)
`WindowManager` singleton pattern follow karta hai aur host OS par desktop window instantiate karta hai.

```python
import os
from typing import Optional
import webview
from pydantic import BaseModel
from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.lifecycle import WindowLifecycleHandler
from deskai.bridge.utils import get_ephemeral_port, generate_session_token

class WindowConfig(BaseModel):
    title: str = "DeskAI Studio"
    width: int = 1440
    height: int = 900
    min_width: int = 1024
    min_height: int = 680
    resizable: bool = True
    frameless: bool = False             # Native OS window decorations enabled
    background_color: str = "#0a0c12"
    confirm_close: bool = True
    text_select: bool = True
    workspace_root: str = "/mnt/Data/Workspaces/Projects/DeskAI"

class WindowManager:
    _instance: Optional['WindowManager'] = None
    window: Optional[webview.Window] = None

    def __init__(self, config: WindowConfig):
        self.config = config
        self.port = get_ephemeral_port()
        self.token = generate_session_token()
        self.api = DesktopBridgeAPI(self, self.config.workspace_root)
        self.lifecycle = WindowLifecycleHandler(self)

    def initialize_window(self) -> webview.Window:
        target_url = f"http://127.0.0.1:{self.port}/?token={self.token}"
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
        # Linux hardware acceleration & NVIDIA crash fixes
        os.environ["GDK_BACKEND"] = "x11,wayland"
        os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"
        webview.start(gui="gtk", debug=debug)
```

---

### 3.2 `DesktopBridgeAPI` Class (`api.py`) & Standardized Error Taxonomy

Har bridge method `BridgeResponse` envelope return karta hai with standardized error taxonomy:

```python
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import webview

class ErrorCode:
    ERR_SANDBOX_VIOLATION = "ERR_SANDBOX_VIOLATION"
    ERR_DIALOG_CANCELLED = "ERR_DIALOG_CANCELLED"
    ERR_FILE_NOT_FOUND = "ERR_FILE_NOT_FOUND"
    ERR_WIN_CONTROL_FAILED = "ERR_WIN_CONTROL_FAILED"
    ERR_INTERNAL = "ERR_INTERNAL"

class BridgeResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager', workspace_root: str):
        self._manager = manager
        self.workspace_root = os.path.realpath(workspace_root)

    def _assert_within_workspace(self, path: str) -> str:
        """Path traversal attacks ko block karne ke liye realpath check karta hai."""
        real_path = os.path.realpath(path)
        if not real_path.startswith(self.workspace_root):
            raise PermissionError(f"Access denied: {path} is outside workspace boundary.")
        return real_path

    def open_directory_dialog(self, title: str = "Select Project Folder") -> Dict[str, Any]:
        """Native GTK Folder Picker dialog open karta hai."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                directory=True
            )
            selected_path = result[0] if result and len(result) > 0 else None
            return BridgeResponse(success=True, data={"path": selected_path}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def open_file_dialog(
        self, 
        file_types: List[str] = ("Supported Files (*.py;*.js;*.html;*.json;*.md)", "All Files (*.*)"),
        allow_multiple: bool = False
    ) -> Dict[str, Any]:
        """Native GTK File Picker dialog open karta hai."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=allow_multiple,
                directory=False,
                file_types=file_types
            )
            return BridgeResponse(success=True, data={"files": list(result) if result else []}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        """System clipboard par string copy karta hai."""
        try:
            self._manager.window.set_clipboard(text)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_INTERNAL).dict()

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
                win.destroy()
            return BridgeResponse(success=True, data={"action": action}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code=ErrorCode.ERR_WIN_CONTROL_FAILED).dict()
```

---

## 4. Lifecycle & Two-Phase Teardown State Machine

```
   [START]
      │
      ▼
┌─────────────┐
│ INITIALIZING│ ➔ Allocates ephemeral port, token & initializes SQLite WAL database
└──────┬──────┘
      │
      ▼
┌─────────────┐
│   LOADED    │ ➔ window.events.loaded fires (Initial UI handshake complete)
└──────┬──────┘
      │
      ▼
┌─────────────┐
│   ACTIVE    │ ➔ Interactive session, CodeMirror 6 editor & WebSocket streaming active
└──────┬──────┘
      │ User clicks 'X'
      ▼
┌─────────────┐
│   CLOSING   │ ➔ window.events.closing (PHASE 1: Check dirty/unsaved buffers)
└──────┬──────┘   * If user cancels dialog: return False (Abort close)
      │           * If confirmed: return True (Proceed)
      ▼
┌─────────────┐
│   CLOSED    │ ➔ window.events.closed (PHASE 2: Irreversible Teardown)
└─────────────┘   * Commit SQLite pending transactions & close connection
                  * Terminate background worker processes
                  * Clean exit with status code 0
```

### Lifecycle Implementation (`lifecycle.py`):
```python
class WindowLifecycleHandler:
    def __init__(self, manager: 'WindowManager'):
        self.manager = manager

    def attach_hooks(self, window: webview.Window):
        window.events.loaded += self.on_loaded
        window.events.closing += self.on_closing
        window.events.closed += self.on_closed

    def on_loaded(self):
        print("[DeskAI] PyWebView native container mounted.")

    def on_closing(self) -> bool:
        """Phase 1: Checks for unsaved user modifications before exit."""
        # Query editor dirty state if needed
        return True  # True allows window to proceed to closed state

    def on_closed(self):
        """Phase 2: Irreversible system flush & daemon termination."""
        print("[DeskAI] Window closed. Flushing database & shutting down.")
        # 1. Flush SQLite WAL logs
        # 2. Terminate background threads & workers
        # 3. Clean exit
```
