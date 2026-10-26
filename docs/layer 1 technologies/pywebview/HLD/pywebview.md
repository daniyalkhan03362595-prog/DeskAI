# Layer 1 Technology HLD: PyWebView Desktop Wrapper & Native Bridge Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Native Shell)** mein use hone wali **PyWebView** library ki mukammal **High-Level Design (HLD)** architecture, native GTK/WebView2 integration, race-free socket handover, token-to-cookie authentication, aur secure IPC bridge ko **Roman Urdu** mein bayan karta hai.

---

## 1. Executive Summary (Native Wrapper Falsafa)
DeskAI ko desktop application banane ke liye Electron ya Chromium-based heavy frameworks ke bajaye **PyWebView** choose kiya gaya hai.

### Is Decision ke Fawaid (Electron vs PyWebView):
1. **Zero Chromium Bloat:** Electron har app ke sath 150MB+ ka Chromium aur Node.js runtime ship karta hai. PyWebView OS ke native **WebKitGTK** (Linux) / **WebView2** (Windows) engine ko direct leverage karta hai.
2. **Massive Memory Savings:** Electron apps 600MB+ RAM leti hain. PyWebView ke sath DeskAI ka full UI process target **~140 MB RAM** hai.
3. **Hardware Acceleration:** Native OS GPU rendering pipeline se animations aur scrolling 60 FPS par smooth render hoti hain.
4. **Instant Cold Start:** Target ~0.35s ke andar desktop window interactive ho jati hai.

---

## 2. Window Container Initialization Architecture

Application ka desktop window race-free socket aur token-to-cookie flow ke sath initialize hota hai:

```python
import os
import sys
import socket
import secrets
import webview

# 1. Platform Guards
if sys.platform.startswith("linux"):
    os.environ.setdefault("GDK_BACKEND", "x11,wayland")
    if os.path.exists("/proc/driver/nvidia") and os.getenv("DESKAI_DISABLE_DMABUF", "1") == "1":
        os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] = "1"

# 2. Race-Free Listening Socket Allocation
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('127.0.0.1', 0))
sock.listen(128)
dynamic_port = sock.getsockname()[1]

# 3. Cryptographic Launch Secret
session_token = secrets.token_urlsafe(32)

# 4. Create PyWebView Window (Entrypoint: /auth/redeem?token=...)
window = webview.create_window(
    title='DeskAI Studio',
    url=f'http://127.0.0.1:{dynamic_port}/auth/redeem?token={session_token}',
    width=1440,
    height=900,
    min_size=(1024, 680),
    frameless=True,  # Modern custom IDE header & client-side decorations
    background_color='#121315'
)
```

---

## 3. Char Bunyadi PyWebView HLD Components

### Component 1: Python-JavaScript Native OS Bridge (`js_api`)
* **Strict Concern Separation:** `window.pywebview.api` sirf native OS functions (Folder Pickers, File Dialogs, System Clipboard, Notifications, External Link Opening) ke liye reserved hai.
* **Sandbox Security (`commonpath`):** Bridge ke andar aane wale tamam file paths ko `os.path.commonpath([real_path, workspace_root]) == workspace_root` se check kiya jata hai taake workspace directory se bahar koi arbitrary read/write ya traversal attack na ho sake.
* **External Link Guard:** Chat ya UI mein aane wale web links ko PyWebView ke andar load hone se roka jata hai aur direct OS ke default browser (`webbrowser.open`) par dispatch kiya jata hai.

### Component 2: Token-to-Cookie Redemption & Host Security
* **HttpOnly Cookie Exchange:** Initial URL token ko first request par `HttpOnly; SameSite=Strict` cookie mein redeem kar ke clean URL par redirect kiya jata hai. Is se sub-resources (`<link>`, `<script>`) aur WebSockets bina custom headers ke authenticated rehte hain.
* **DNS Rebinding Defense:** Server incoming `Host` header (`127.0.0.1:{port}`) aur `Origin` check karta hai taake local machine par chalne wale doosre browsers loopback API ko target na kar sakein.

### Component 3: Deadlock-Free Dirty Buffer Lifecycle
* **JS-Pushed Dirty Flag:** UI dirty buffer hone par flag Python ko push karta hai. Window close hone par Python main thread GTK event loop mein deadlock kiye baghair confirmation check execute karta hai.

### Component 4: Cross-Platform Compatibility
* Linux par WebKitGTK aur Windows par WebView2 runtime automatically select hota hai. Linux par Wayland aur X11 dono par smooth fallback ensure kiya gaya hai.
