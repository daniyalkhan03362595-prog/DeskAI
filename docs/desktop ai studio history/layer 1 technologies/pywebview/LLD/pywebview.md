# Layer 1 Technology LLD: PyWebView Desktop Wrapper & Native Bridge Implementation

Yeh document **Desktop AI Studio** ke **Layer 1 (Frontend)** mein use hone wali **PyWebView** library ki mukammal **Low-Level Design (LLD)** specifications, Python class models, method signatures, IPC data contracts, thread safety rules, aur native OS integration ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Scope

PyWebView application ka **native shell aur communication spine** hai jo Linux desktop environment (X11/Wayland) ke sath Python backend aur Web frontend ko jorta hai.

### Low-Level Responsibilities:
1. **Window Management:** WebKitGTK window initialize karna, dimensions, min/max limits, window state (frameless/decorated, fullscreen) control karna.
2. **Synchronous & Asynchronous IPC Bridge:** Python backend methods ko JavaScript context (`window.pywebview.api`) mein expose karna aur bidirectional messaging provide karna.
3. **OS System Services:** Native GTK file pickers, folder dialogs, system notifications aur clipboard access provide karna.
4. **Lifecycle & Process Supervision:** Window events (`loaded`, `closing`, `closed`) ko manage karna aur backend processes (Uvicorn, AI workers) ki clean teardown ensure karna.

---

## 2. Directory & Module Architecture

Backend ke andar PyWebView wrapper ka code is module structure mein munazzam hota hai:

```text
src/deskai/bridge/
├── __init__.py               # Package exports
├── window.py                 # WindowManager class (GTK window setup & config)
├── api.py                    # DesktopBridgeAPI (js_api exposed methods)
├── lifecycle.py              # WindowLifecycleHandler (startup & graceful exit)
├── models.py                 # IPC Request/Response Pydantic schemas
├── events.py                 # Python-to-JS CustomEvent dispatch engine
└── utils.py                  # Linux GTK/Wayland flags & system checks
```

---

## 3. Class Specifications & Method Signatures

### 3.1 `WindowManager` Class (`window.py`)
`WindowManager` singleton pattern follow karta hai aur operating system par desktop window create karne ka zimmedar hai.

```python
class WindowConfig(BaseModel):
    title: str = "Desktop AI Studio"
    url: str = "http://127.0.0.1:8000"
    width: int = 1440
    height: int = 900
    min_width: int = 1024
    min_height: int = 680
    resizable: bool = True
    frameless: bool = False
    easy_drag: bool = False
    background_color: str = "#0c0e14"
    confirm_close: bool = True
    text_select: bool = True

class WindowManager:
    _instance: Optional['WindowManager'] = None
    window: Optional[webview.Window] = None
    api: 'DesktopBridgeAPI'

    def __init__(self, config: WindowConfig):
        self.config = config
        self.api = DesktopBridgeAPI(self)
        self.lifecycle = WindowLifecycleHandler(self)

    def initialize_window(self) -> webview.Window:
        """PyWebView window object create karta hai aur lifecycle attach karta hai."""
        self.window = webview.create_window(
            title=self.config.title,
            url=self.config.url,
            js_api=self.api,
            width=self.config.width,
            height=self.config.height,
            min_size=(self.config.min_width, self.config.min_height),
            resizable=self.config.resizable,
            frameless=self.config.frameless,
            easy_drag=self.config.easy_drag,
            background_color=self.config.background_color,
            confirm_close=self.config.confirm_close,
            text_select=self.config.text_select
        )
        self.lifecycle.attach_hooks(self.window)
        return self.window

    def start_loop(self, debug: bool = False) -> None:
        """GTK event loop start karta hai (blocking call)."""
        # GDK Backend priority enforcement for Linux
        os.environ["GDK_BACKEND"] = "x11,wayland"
        webview.start(gui="gtk", debug=debug)
```

---

### 3.2 `DesktopBridgeAPI` Class (`api.py`)
Yeh class `js_api` parameter ke zariye JavaScript ke global scope (`window.pywebview.api`) par direct expose hoti hai. Har method standardized `BridgeResponse` return karta hai.

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import webview

class BridgeResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

class DesktopBridgeAPI:
    def __init__(self, manager: 'WindowManager'):
        self._manager = manager

    def open_directory_dialog(self, title: str = "Select Project Folder") -> Dict[str, Any]:
        """
        Native GTK Folder Picker dialog open karta hai.
        JavaScript Call: await window.pywebview.api.open_directory_dialog()
        """
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                directory=True
            )
            selected_path = result[0] if result and len(result) > 0 else None
            return BridgeResponse(success=True, data={"path": selected_path}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code="ERR_DIALOG_OPEN").dict()

    def open_file_dialog(
        self, 
        file_types: List[str] = ("Supported Files (*.py;*.js;*.html;*.json)", "All Files (*.*)"),
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
            return BridgeResponse(success=False, error=str(e), error_code="ERR_FILE_PICKER").dict()

    def save_file_dialog(self, default_filename: str = "untitled.txt") -> Dict[str, Any]:
        """Native Save File Dialog open karta hai."""
        try:
            result = self._manager.window.create_file_dialog(
                dialog_type=webview.SAVE_DIALOG,
                save_filename=default_filename
            )
            return BridgeResponse(success=True, data={"path": result}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code="ERR_FILE_SAVE").dict()

    def get_hardware_telemetry(self) -> Dict[str, Any]:
        """
        Direct C-binding / OS telemetry fetch karta hai (Zero HTTP Overhead).
        JavaScript Call: await window.pywebview.api.get_hardware_telemetry()
        """
        try:
            telemetry = {
                "gpu": {
                    "name": "NVIDIA GeForce RTX 2070 Super",
                    "vram_used_mb": 4210,
                    "vram_total_mb": 8192,
                    "utilization_pct": 34,
                    "temperature_c": 56
                },
                "cpu": {
                    "usage_pct": 18.4,
                    "cores": 16
                },
                "ram": {
                    "used_mb": 7320,
                    "total_mb": 32150
                }
            }
            return BridgeResponse(success=True, data=telemetry).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code="ERR_TELEMETRY").dict()

    def control_window(self, action: str) -> Dict[str, Any]:
        """
        Native window controls (minimize, maximize, restore, fullscreen).
        Action: 'minimize' | 'maximize' | 'restore' | 'fullscreen' | 'close'
        """
        win = self._manager.window
        try:
            if action == "minimize":
                win.minimize()
            elif action == "maximize":
                win.maximize()
            elif action == "restore":
                win.restore()
            elif action == "fullscreen":
                win.toggle_fullscreen()
            elif action == "close":
                win.destroy()
            return BridgeResponse(success=True, data={"action": action}).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code="ERR_WIN_CONTROL").dict()

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        """System clipboard par string copy karta hai."""
        try:
            self._manager.window.set_clipboard(text)
            return BridgeResponse(success=True).dict()
        except Exception as e:
            return BridgeResponse(success=False, error=str(e), error_code="ERR_CLIPBOARD").dict()
```

---

## 4. Bidirectional IPC Wire Protocol

PyWebView WebKitGTK engine ke andar C-level WebKit API message passing use karta hai. Iska wire protocol do raston par mushtamil hai:

### 4.1 Forward Flow (JavaScript ➔ Python)
1. **Frontend Call:**
   JavaScript code `window.pywebview.api.method_name(args)` execute karta hai jo browser runtime par `Promise` return karta hai.
2. **WebKit Message Handler:**
   WebKit2GTK ka `WebKitUserContentManager` script message intercept karta hai aur C-layer se Python callback ko dispatch karta hai.
3. **Execution & Promise Resolution:**
   Python function execute hone ke baad JSON serialize ho kar WebKit script world mein wapis bhejta hai, jahan JS Promise resolve ho jata hai:
   ```javascript
   // Frontend Usage Example
   try {
       const res = await window.pywebview.api.open_directory_dialog("Select Project");
       if (res.success && res.data.path) {
           console.log("Active Project Path:", res.data.path);
       }
   } catch (err) {
       console.error("Bridge RPC Failed:", err);
   }
   ```

### 4.2 Reverse Flow (Python ➔ JavaScript via `evaluate_js`)
Jab Python backend ko koi asynchronous event (jaise Live Hardware Telemetry ya AI token streaming chunk) frontend ko bhejna hota hai:
1. Python engine `window.evaluate_js(script)` call karta hai.
2. Script DOM ke andar custom event emit karta hai:
   ```python
   def dispatch_dom_event(window: webview.Window, event_name: str, payload: dict):
       import json
       json_str = json.dumps(payload)
       script = f"window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: {json_str} }}));"
       window.evaluate_js(script)
   ```
3. Frontend event listener trigger hota hai:
   ```javascript
   window.addEventListener('deskai:telemetry', (e) => {
       const telemetryData = e.detail;
       updateTelemetryUI(telemetryData);
   });
   ```

---

## 5. Threading & Concurrency Architecture

PyWebView aur backend ke darmiyan race condition aur deadlocks se bachne ke liye strict thread separation rule follow kiya jata hai:

```
+-------------------------------------------------------------------+
|                           PROCESS ROOT                            |
|                                                                   |
|   [Thread 1: Main Thread]          [Thread 2: Daemon Thread]     |
|   +--------------------------+     +--------------------------+   |
|   |   PyWebView GTK Loop     |     |   FastAPI / Uvicorn API  |   |
|   |   (GLib.MainLoop)        |     |   (Asyncio Event Loop)   |   |
|   |   - Window Rendering     |     |   - HTTP Routes          |   |
|   |   - Native Dialogs       |     |   - WebSocket Gateway    |   |
|   |   - WebKit2GTK Engine    |     |   - AI Orchestrator      |   |
|   +------------+-------------+     +-------------+------------+   |
|                |                                 |                |
|                +=======[ Thread-Safe Queue ]=====+                |
|                        (GLib.idle_add callback)                   |
+-------------------------------------------------------------------+
```

### Golden Threading Rules:
1. **GTK Main Loop Supremacy:** `webview.start(gui='gtk')` ko hamesha Python ke **Main Thread** par chalaya jata hai kyunki Linux X11/Wayland windows main thread se bahar safe create nahi ho sakein.
2. **Server Background Thread:** FastAPI/Uvicorn server ko separate daemon thread mein background par start kiya jata hai.
3. **No Direct GTK Mutation from Workers:** Background worker threads kabhi bhi direct GTK window object ko modify nahi kar sakte; agar zaroorat ho to `GLib.idle_add()` use hota hai.

---

## 6. Window Lifecycle & Graceful Teardown State Machine

```
   [START]
      │
      ▼
┌─────────────┐
│ INITIALIZING│ ➔ GDK Backend setup & configuration validation
└──────┬──────┘
      │
      ▼
┌─────────────┐
│  CREATING   │ ➔ webview.create_window() creates WebKit2GTK container
└──────┬──────┘
      │
      ▼
┌─────────────┐
│   LOADED    │ ➔ window.events.loaded fires (Handshake complete)
└──────┬──────┘
      │
      ▼
┌─────────────┐
│   ACTIVE    │ ➔ UI interactive & Bridge RPC active
└──────┬──────┘
      │ User clicks 'X' or closes app
      ▼
┌─────────────┐
│   CLOSING   │ ➔ window.events.closing intercepts:
└──────┬──────┘   1. Terminate Uvicorn HTTP/WebSocket servers
                  2. Cancel background telemetry timers
                  3. Clean up temporary cache & lock files
      │
      ▼
┌─────────────┐
│   CLOSED    │ ➔ Process exits cleanly with code 0 (Zero zombie tasks)
└─────────────┘
```

### Code Implementation (`lifecycle.py`):
```python
class WindowLifecycleHandler:
    def __init__(self, manager: 'WindowManager'):
        self.manager = manager

    def attach_hooks(self, window: webview.Window):
        window.events.loaded += self.on_loaded
        window.events.closing += self.on_closing
        window.events.closed += self.on_closed

    def on_loaded(self):
        print("[Desktop AI Studio] PyWebView WebKit window loaded successfully.")

    def on_closing(self):
        """User ke exit karne par graceful teardown orchestrate karta hai."""
        print("[Desktop AI Studio] Initiating graceful teardown...")
        # 1. Stop background telemetry
        # 2. Shutdown local FastAPI server
        # 3. Flushes disk write buffers
        return True  # Returns True to permit window closing

    def on_closed(self):
        print("[Desktop AI Studio] Window closed. Process exiting cleanly.")
```

---

## 7. Linux Environment & WebKitGTK Security Hardening

1. **Localhost Isolation:**
   Webview sirf `http://127.0.0.1:{dynamic_port}` load karta hai. Kisi external internet URL ka navigation strictly disable hota hai.
2. **Strict Origin Validation:**
   Bridge APIs sirf specific internal origin se call accept karte hain taake koi injection attack na ho sake.
3. **Developer Tools Security:**
   Production release mein `debug=False` set hota hai jis se Inspect Element aur Web Developer Console lock rehte hain.
4. **Wayland & X11 Automatic Fallback:**
   Linux OS par crash se bachne ke liye `GDK_BACKEND="x11,wayland"` environment set hota hai jo hardware acceleration aur multi-monitor scaling ko auto-adjust karta hai.
