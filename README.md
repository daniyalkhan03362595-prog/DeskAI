# DeskAI ⚡

> **An ultra-lean, 100% private, autonomous desktop AI engineering studio.**  
> Built with Python (PyWebView) + Semantic HTML5/CSS3/ES Modules + CodeMirror 6 + Local Ollama (Qwen 2.5 Coder 7B) + In-Process SQLite (sqlite-vec).

---

## 🎯 Architecture Philosophy

DeskAI is engineered from first principles to solve the heavy memory bloat and cloud privacy leaks of modern developer tooling:

* **Zero Electron Bloat:** Uses native OS WebKitGTK (Linux) and WebView2 (Windows) via PyWebView. UI memory footprint is **~140 MB RAM** instead of 600MB+ Chromium overhead.
* **Zero Docker / Zero PostgreSQL:** Complete replacement of external containerized databases with embedded **SQLite 3 in WAL mode** and the **`sqlite-vec` C-extension** for high-dimensional vector search (~15 MB RAM, 0 external network ports).
* **Hardware-Accelerated Local Intelligence:** Integrates with local **Ollama** running **Qwen 2.5 Coder 7B (Q4_K_M)** on NVIDIA CUDA. Realistic VRAM footprint is **~4.7 GB**, leaving 3.3 GB free headroom on an 8GB RTX GPU.
* **Hardened Security & Sandboxed IPC:**
  * **Dynamic Ephemeral Port:** Python automatically allocates a random loopback port on startup.
  * **Cryptographic Session Token:** All HTTP requests and WebSocket handshakes require a per-launch 32-byte secret token.
  * **Strict Origin & CSP:** Blocks external browser connections, DNS rebinding, and untrusted scripts.
  * **DOMPurify Sanitization:** All model-generated markdown is sanitized prior to DOM insertion.
  * **Filesystem & Terminal Sandboxing:** Realpath boundary verification against workspace root with human-in-the-loop approvals for sensitive commands.

---

## 🏗️ Architecture & Layer Roadmap

```text
┌──────────────────────────────────────────────────────────────┐
│                    Layer 1: Presentation & Native Shell       │
│  PyWebView 4+ | HTML5 Semantic DOM | CSS3 Design Tokens      │
│  Vanilla ES2022 Modules | CodeMirror 6 Editor | DOMPurify    │
└──────────────────────────────┬───────────────────────────────┘
                               │ Authenticated IPC & Streaming
┌──────────────────────────────▼───────────────────────────────┐
│                    Layer 2: Storage & Knowledge Engine       │
│  SQLite 3 (WAL mode) | sqlite-vec HNSW | In-Process Memory   │
│  AST File Chunking | Semantic Code Retrieval                 │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Layer 3: Local Neural Brain (Inference)   │
│  Ollama Daemon | Qwen 2.5 Coder 7B | CUDA Acceleration       │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Layer 4: Autonomous Agent Orchestrator    │
│  Unified Execution Card (UEC) | Diff Engine | Sandbox Runner │
└──────────────────────────────────────────────────────────────┘
```

---

## 📂 Documentation Directory

Detailed specifications in Roman Urdu and English are located under `docs/`:

* **System Architecture (HLD & LLD):**
  * `docs/desktop ai studio history/technologies/HLD/technologies.md`
  * `docs/desktop ai studio history/technologies/LLD/technologies.md`
* **Layer 1 Core Specifications:**
  * **PyWebView Shell:** `docs/desktop ai studio history/layer 1 technologies/pywebview/`
  * **JavaScript Runtime:** `docs/desktop ai studio history/layer 1 technologies/javascript/`
  * **Semantic HTML5:** `docs/desktop ai studio history/layer 1 technologies/html5/`
  * **CSS3 Design System:** `docs/desktop ai studio history/layer 1 technologies/css3/`
* **Visual Diagrams & Figcraft Canvases:** Available under `designs/`.

---

## 🚀 Quick Setup & Dependencies

### Prerequisites
* Linux (Ubuntu 22.04+ / Arch / Debian) or Windows 10/11
* Python 3.10+
* WebKit2GTK 2.40+ (Linux) or WebView2 runtime (Windows)
* NVIDIA GPU with CUDA 12+ (RTX 2070 Super 8GB or higher recommended)
* [Ollama](https://ollama.com) installed with `qwen2.5-coder:7b`

### Installation
```bash
git clone https://github.com/daniyalkhan03362595-prog/DeskAI.git
cd DeskAI
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 🛡️ Security & Threat Model Summary
1. **Network Boundary:** Web server listens strictly on `127.0.0.1` on a dynamic port; external LAN/WAN listening is forbidden.
2. **WebSocket Handshake:** Unauthenticated connections without `?token=<secret>` or invalid origins are rejected immediately (HTTP 403 / Close code 1008).
3. **Command Execution:** Terminal runner runs exclusively with current working directory locked to `workspace_root`.
4. **Content Security Policy:** `default-src 'self'; script-src 'self'; connect-src 'self' ws://127.0.0.1:* http://127.0.0.1:*; object-src 'none'; base-uri 'none'; form-action 'none'`.

---

## 📜 License
Distributed under the **MIT License**. See `LICENSE` for details.
