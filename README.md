# DeskAI — Layer 1: Desktop Shell & Presentation Layer ⚡

> **An ultra-lightweight, high-performance desktop AI shell and presentation environment.**  
> Built with Python (PyWebView 4+) + Semantic HTML5 + Pure CSS3 Design Tokens + Vanilla ES2022 Modules + CodeMirror 6 Editor.

---

## 🎯 Layer 1 Architecture & Scope

DeskAI Layer 1 serves as the foundational desktop interface, native OS integration shell, and real-time interaction surface:

* **Zero Electron Bloat:** Uses native OS WebKitGTK (Linux) and WebView2 (Windows) via PyWebView. UI memory footprint is **~140 MB RAM** instead of 600MB+ Chromium overhead.
* **Semantic HTML5 & Pure CSS3:** Zero-dependency layout with strict CSS containment (`contain: layout paint`), hardware-accelerated transforms, and WCAG AA contrast standards.
* **CodeMirror 6 Embedded Editor:** Virtualized scrolling, multi-tab buffer tracking, syntax highlighting, and dirty state management.
* **Deep Reactive Store (`state.js`):** Recursive `Proxy` observable architecture ensuring fine-grained updates without virtual DOM overhead.
* **Hardened Security & Sandboxed IPC:**
  * **Dynamic Ephemeral Port:** Python allocates a random loopback port on launch (`127.0.0.1:{dynamic_port}`).
  * **Cryptographic Session Token:** All HTTP requests and WebSocket connections require a per-launch 32-byte secret token (`X-DeskAI-Token`).
  * **Strict Origin & CSP:** Blocks external browser connections, DNS rebinding, and untrusted scripts via HTTP headers.
  * **DOMPurify Sanitization:** All markdown output and external content is strictly sanitized prior to DOM insertion.
  * **Path Canonicalization:** Bridge API canonicalizes all file paths against the workspace root with `os.path.realpath()`.

---

## 🏗️ Layer 1 System Architecture

```text
+---------------------------------------------------------------------------------------------------+
|                                      HOST RUNTIME (OS)                                            |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [PRESENTATION CLIENT] (WebKitGTK / WebView2 | RAM: ~140 MB)                                 |  |
|  | - Window Shell: PyWebView Container (Frameless / Native Controls)                           |  |
|  | - Layout: Semantic HTML5 DOM (No Virtual DOM overhead)                                     |  |
|  | - Styling: Pure CSS3 Design Tokens & Hardware-Accelerated Keyframes                         |  |
|  | - Code Editor: Embedded CodeMirror 6 (Virtual Scrolling & Multi-Buffer Tabs)               |  |
|  | - Client Logic: Native ES Modules (Recursive Deep Proxy, rAF Streamer, Action Router)       |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 |                                                 |
|                   Native OS IPC Bridge          | Authenticated WebSocket (Token-Guarded)         |
|                   (window.pywebview.api)        | (ws://127.0.0.1:{dynamic_port}/ws?token=xyz)    |
|                                                 v v                                               |
|  +---------------------------------------------------------------------------------------------+  |
|  | [LOCAL GATEWAY & DESKTOP SUPERVISOR] (Python 3.10+ | FastAPI / Uvicorn ASGI | RAM: ~105 MB)   |  |
|  | - Web Server: Ephemeral Port Listener (127.0.0.1:{dynamic_port})                            |  |
|  | - Security Guard: Session Token Validator & Strict Localhost Origin Checker                 |  |
|  | - Desktop Bridge: Native File/Folder Dialogs, Window Min/Max/Close, System Clipboard        |  |
|  | - Sandbox Guard: Workspace Root Boundary Enforcement (os.path.realpath)                     |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 📂 Layer 1 Specifications Directory

Detailed specifications in Roman Urdu and English are located under `docs/layer 1 technologies/`:

* **PyWebView Shell:**
  * [HLD Specification](docs/layer%201%20technologies/pywebview/HLD/pywebview.md)
  * [LLD Specification](docs/layer%201%20technologies/pywebview/LLD/pywebview.md)
* **Vanilla JavaScript Runtime:**
  * [HLD Specification](docs/layer%201%20technologies/javascript/HLD/javascript.md)
  * [LLD Specification](docs/layer%201%20technologies/javascript/LLD/javascript.md)
* **Semantic HTML5:**
  * [HLD Specification](docs/layer%201%20technologies/html5/HLD/html5.md)
  * [LLD Specification](docs/layer%201%20technologies/html5/LLD/html5.md)
* **CSS3 Design System:**
  * [HLD Specification](docs/layer%201%20technologies/css3/HLD/css3.md)
  * [LLD Specification](docs/layer%201%20technologies/css3/LLD/css3.md)
* **Visual Diagrams & Figcraft Canvases:** Available under `designs/layer 1 technologies/`.

---

## 🚀 Quick Setup & Dependencies

### Prerequisites
* Linux (Ubuntu 22.04+ / Arch / Debian) or Windows 10/11
* Python 3.10+
* WebKit2GTK 2.40+ (Linux) or WebView2 runtime (Windows)

### Installation
```bash
git clone https://github.com/daniyalkhan03362595-prog/DeskAI.git
cd DeskAI
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Running Contract Tests
```bash
python -m unittest discover -s tests
```

---

## 🛡️ Security & Threat Model Summary
1. **Network Boundary:** Web server listens strictly on `127.0.0.1` on an ephemeral dynamic port; external network listening is strictly disabled.
2. **WebSocket Handshake:** Unauthenticated connections without `?token=<secret>` or invalid origins are rejected immediately (HTTP 403 / Close code 1008).
3. **Filesystem Boundary:** All file and folder operations canonicalize paths against `workspace_root`.
4. **Content Security Policy:** `default-src 'self'; script-src 'self'; connect-src 'self' ws://127.0.0.1:* http://127.0.0.1:*; object-src 'none'; base-uri 'none'; form-action 'none'`.

---

## 📜 License
Distributed under the **MIT License**. See `LICENSE` for details.
