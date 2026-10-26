# DeskAI — Layer 1: Desktop Shell & Presentation Layer ⚡

> **An ultra-lightweight, high-performance desktop AI shell and presentation environment.**  
> Built with Python (PyWebView 4+) + Semantic HTML5 + Pure CSS3 Design Tokens + Vanilla ES2022 Modules + CodeMirror 6 Editor.

---

## 🎯 Layer 1 Architecture & Scope

DeskAI Layer 1 serves as the foundational desktop interface, native OS integration shell, and real-time interaction surface:

* **Zero Electron Bloat:** Uses native OS WebKitGTK (Linux) and WebView2 (Windows) via PyWebView. UI memory footprint target is **~140 MB RAM** instead of 600MB+ Chromium overhead. Cold startup target is **~0.35s Time-to-Interactive**.
* **Semantic HTML5 & Pure CSS3:** Zero-dependency layout with strict CSS containment (`contain: layout paint`), hardware-accelerated transforms, and WCAG AA contrast standards (all text contrast >= 5.3:1).
* **CodeMirror 6 Vendor Bundle:** Virtualized scrolling, multi-tab buffer tracking, syntax highlighting, and dirty state management pre-bundled into a self-contained vendor file (`static/vendor/codemirror.bundle.js`).
* **Deep Reactive Store (`state.js`):** Recursive `Proxy` observable architecture with WeakMap caching (`state.execution === state.execution`) and ancestor notification bubbling.
* **Hardened Security & Sandboxed IPC:**
  * **Race-Free Dynamic Port:** Python binds a listening loopback socket (`127.0.0.1:0`) and passes the socket directly to the server.
  * **Token-to-Cookie Redemption:** Launch URL token is redeemed on initial request for an `HttpOnly; SameSite=Strict` cookie, redirecting to a clean URL. Sub-resources (`<link>`, `<script>`) and WebSockets authenticate automatically via cookie.
  * **Host & Origin Validation:** Rejects DNS rebinding and cross-origin attacks by verifying incoming `Host` (`127.0.0.1:{port}`) and `Origin` headers.
  * **Exact-Port CSP:** Injects dynamic port per launch (`connect-src 'self' ws://127.0.0.1:{port} http://127.0.0.1:{port}; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-eval'; object-src 'none'; base-uri 'none'; form-action 'none'`).
  * **DOMPurify Sanitization:** All markdown output and external content is strictly sanitized with explicit tag allowlists prior to DOM insertion.
  * **Path Sandboxing (`commonpath`):** Bridge API canonicalizes all file paths against the runtime `workspace_root` with `os.path.commonpath()` (preventing `/DeskAI-secrets` traversal vulnerabilities).
  * **External Link Sandbox:** Web links in chat are intercepted and dispatched to the OS default browser (`webbrowser.open`), preventing off-origin navigation in the desktop shell.

---

## 🏗️ Layer 1 System Architecture

```text
+---------------------------------------------------------------------------------------------------+
|                                      HOST RUNTIME (OS)                                            |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [PRESENTATION CLIENT] (WebKitGTK / WebView2 | Target RAM: ~140 MB)                          |  |
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
|  | [DESKTOP SUPERVISOR / SHELL SERVER] (Python 3.11+ | FastAPI / Uvicorn ASGI | Target: ~105 MB) |  |
|  | - Web Server: Bound Socket Listener (127.0.0.1:{dynamic_port})                              |  |
|  | - Security Guard: Host/Origin Verifier, Cookie Issuer & Exact-Port CSP Injector             |  |
|  | - Desktop Bridge: Native File/Folder Dialogs, Window Min/Max/Close, External Link Opener    |  |
|  | - Sandbox Guard: Workspace Root Boundary Enforcement (os.path.commonpath)                   |  |
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
* Python 3.11+
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

## 🛡️ Security & Threat Model Summary
1. **Network Boundary:** Web server listens strictly on loopback (`127.0.0.1`) on an ephemeral dynamic port; external network listening is strictly disabled.
2. **Session Authentication:** Token-to-cookie redemption pattern ensures session tokens are not leaked via URLs or browser histories.
3. **Host & Origin Verification:** In-bound requests must match exact `127.0.0.1:{port}` host to prevent DNS rebinding.
4. **Filesystem Boundary:** All file and folder operations canonicalize paths against `workspace_root` using `commonpath` to prevent path traversal outside workspace bounds.
5. **Content Security Policy:** Exact dynamic port enforced per launch. Nonces supported for runtime editor styles.
6. **External Navigation Protection:** Native bridge intercepts `a[href]` links to prevent the shell from navigating off-origin.

---

## 📜 License
Distributed under the **MIT License**. See `LICENSE` for details.
