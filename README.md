# DeskAI — Layer 1: Desktop Shell & Presentation Layer ⚡

[![DeskAI Layer 1 CI](https://github.com/daniyalkhan03362595-prog/DeskAI/actions/workflows/ci.yml/badge.svg)](https://github.com/daniyalkhan03362595-prog/DeskAI/actions/workflows/ci.yml)

> **An ultra-lightweight, high-performance desktop AI shell and presentation environment.**  
> Built with Python (PyWebView 5.0+) + Semantic HTML5 + Pure CSS3 Design Tokens + Vanilla ES2022 Modules + CodeMirror 6 Editor.

---

## 🎯 Layer 1 Architecture & Scope

DeskAI Layer 1 serves as the foundational desktop interface, native OS integration shell, and real-time interaction surface:

* **Zero Electron Bloat:** Uses native OS WebKitGTK (Linux) and WebView2 (Windows) via PyWebView. Measured supervisor cold startup is **< 25 ms** (benchmarkable via `tools/benchmark.py`).
* **Semantic HTML5 & Pure CSS3:** Zero-dependency layout with strict CSS containment (`contain: layout paint`), hardware-accelerated transforms, and WCAG AA contrast standards (all text contrast >= 5.3:1, border non-text contrast >= 3:1).
* **CodeMirror 6 Vendor Bundle:** Virtualized scrolling, multi-tab buffer tracking, syntax highlighting, and dirty state management pre-bundled into a self-contained vendor file (`static/vendor/codemirror.bundle.js`).
* **Deep Reactive Store (`state.js`):** Recursive `Proxy` observable architecture with WeakMap caching (`state.execution === state.execution`), array mutation bubbling, and ancestor notification bubbling.
* **Hardened Security & Sandboxed IPC:**
  * **Race-Free Dynamic Port:** Python binds a listening loopback socket (`127.0.0.1:0`) using `SO_EXCLUSIVEADDRUSE` on Windows and `SO_REUSEADDR` on POSIX.
  * **Token-to-Cookie Redemption:** Launch URL token is redeemed on initial request for an `HttpOnly; SameSite=Strict` cookie, redirecting to a clean URL. Sub-resources (`<link>`, `<script>`) and WebSockets authenticate automatically via cookie.
  * **Host & Origin Validation:** Rejects DNS rebinding and cross-origin attacks by verifying incoming `Host` (`127.0.0.1:{port}`) and `Origin` headers.
  * **Exact-Port CSP:** Injects dynamic port per launch with strict directives (`connect-src 'self' ws://127.0.0.1:{port} http://127.0.0.1:{port}; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`).
  * **DOMPurify Sanitization:** All markdown output and external content is strictly sanitized with explicit tag allowlists prior to DOM insertion.
  * **Path Sandboxing (`commonpath`):** Bridge API canonicalizes all file paths against the runtime `workspace_root` with `os.path.commonpath()` (preventing `/DeskAI-secrets` traversal vulnerabilities), with explicit system directory and home root blocking.
  * **External Link Sandbox:** Web links in chat are intercepted and dispatched to the OS default browser (`webbrowser.open`), preventing off-origin navigation in the desktop shell.

---

## 📊 Implementation & Verification Status

| Subsystem / Feature | Linux (Wayland) | Linux (X11) | Windows (10/11) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Shell Window & Lifecycle** | WebKit2GTK | WebKit2GTK | WebView2 | Automated unit tests (`test_task6_frameless_lifecycle.py`), single-prompt exit guard |
| **Frameless Controls** | GDK `begin_move_drag` | GDK `begin_move_drag` | ctypes `ReleaseCapture` + `WM_NCLBUTTONDOWN` | Verified in unit tests & mock simulation; manual steps in `MANUAL_TEST.md` |
| **Perimeter Resizing** | >= 6px handles | >= 6px handles | >= 6px handles + hit-test | Verified in CSS & unit tests |
| **Token-to-Cookie Auth** | Single-use launch token | Single-use launch token | Single-use launch token | Verified in `test_runtime.py` and `test_task7_security_headers.py` |
| **Security Headers & CSP** | No `'unsafe-inline'`, bridge `'unsafe-eval'` | No `'unsafe-inline'`, bridge `'unsafe-eval'` | No `'unsafe-inline'`, bridge `'unsafe-eval'` | Verified in `test_task7_security_headers.py` |
| **Path Sandboxing** | `commonpath` + disallowed roots | `commonpath` + disallowed roots | Case-insensitive `commonpath` + `SO_EXCLUSIVEADDRUSE` | Verified in `test_task8_path_sandbox.py` |
| **Vendor Integrity** | DOMPurify, Marked, CodeMirror 6 | DOMPurify, Marked, CodeMirror 6 | DOMPurify, Marked, CodeMirror 6 | SHA-256 Manifest Verified in `test_task1_vendor_editor.py` |
| **State & Telemetry** | Deep Proxy bubbling + Real host RAM | Deep Proxy bubbling + Real host RAM | Deep Proxy bubbling + Fallback | Verified in `test_task9_frontend_state.py` |
| **Theme & WCAG AA** | Contrast >= 3:1 non-text, >= 4.5:1 text | Contrast >= 3:1 non-text, >= 4.5:1 text | Contrast >= 3:1 non-text, >= 4.5:1 text | Verified in `test_task10_theme_a11y.py` |

---

## 🏗️ Layer 1 System Architecture

```text
+---------------------------------------------------------------------------------------------------+
|                                      HOST RUNTIME (OS)                                            |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [PRESENTATION CLIENT] (WebKitGTK / WebView2)                                                |  |
|  | - Window Shell: PyWebView Container (Frameless / Native Controls)                           |  |
|  | - Layout: Semantic HTML5 DOM (Full ARIA: role="tablist", "tree", "tabpanel")                |  |
|  | - Styling: Pure CSS3 Design Tokens & Hardware-Accelerated Keyframes                         |  |
|  | - Code Editor: Embedded CodeMirror 6 Vendor Bundle (Virtual Scrolling & Multi-Buffer Tabs)  |  |
|  | - Client Logic: Native ES Modules (WeakMap Deep Proxy, Accumulated Streamer, Action Router) |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 |                                                 |
|                   Native OS IPC Bridge          | Cookie-Authenticated WebSocket                  |
|                   (window.pywebview.api)        | (ws://127.0.0.1:{dynamic_port}/ws)              |
|                                                 v v                                               |
|  +---------------------------------------------------------------------------------------------+  |
|  | [DESKTOP SUPERVISOR / SHELL SERVER] (Python 3.11+ | FastAPI / Uvicorn ASGI)                   |  |
|  | - Web Server: Bound Socket Listener (127.0.0.1:{dynamic_port})                              |  |
|  | - Security Guard: Host/Origin Verifier, Cookie Issuer & Exact-Port CSP Injector             |  |
|  | - Desktop Bridge: Native File/Folder Dialogs, Window Min/Max/Close, External Link Opener    |  |
|  | - Sandbox Guard: Workspace Root Boundary Enforcement (os.path.commonpath)                   |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 🚀 Quick Setup & Dependencies

### Prerequisites
* Linux (Ubuntu 22.04+ / Arch / Debian) or Windows 10/11
* Python 3.11+
* WebKit2GTK 2.40+ (Linux) or WebView2 runtime (Windows)

### Installation
```bash
git clone https://github.com/daniyalkhan03362595-prog/DeskAI.git
cd DeskAI
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Test Suite
```bash
python -m unittest discover -s tests
```

### Benchmarks
To benchmark cold startup and memory metrics:
```bash
python tools/benchmark.py
```

### Vendor Dependencies & Manifest
All client-side third-party assets are pinned, strictly hash-verified against `src/deskai/static/vendor/MANIFEST.json`:
- **DOMPurify 3.4.17**: Sanitizes streamed Markdown output prior to DOM insertion.
- **marked 18.1.2**: Standards-compliant Markdown parser.
- **CodeMirror 6.0.1**: Bundled using `tools/build_vendor.sh` with line numbers, Obsidian Matte dark theme, and syntax highlighting for Python, JavaScript, and Markdown.

To rebuild and verify vendor bundles:
```bash
./tools/build_vendor.sh
```

---

## 📜 License
Distributed under the **MIT License**. See `LICENSE` for details.
