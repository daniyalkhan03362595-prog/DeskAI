# DeskAI — Technologies Integration & Subsystem Interoperability (LLD)

Yeh document **DeskAI** ke tamam subsystems (`PyWebView`, `HTML5/CSS3/JS + CodeMirror 6`, `FastAPI/Uvicorn`, `Ollama/Qwen 7B`, `SQLite/sqlite-vec`) ke aapsi **Low-Level Design (LLD)** integration protocols, dynamic port allocation, IPC wire formats, authentication tokens, memory budgets aur startup/shutdown lifecycle ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Full-Stack System Topology

DeskAI ka architecture lightweight, secure aur fully embedded runtime par mushtamil hai. Koi external Docker daemon ya PostgreSQL service nahi chahiye:

```text
+---------------------------------------------------------------------------------------------------+
|                                      LINUX OS (HOST RUNTIME)                                      |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [SUBSYSTEM 1: DESKTOP CLIENT] (Process PID: ~28100 | RAM: ~140 MB)                          |  |
|  | - Window Shell: PyWebView Container (WebKitGTK on Linux / WebView2 on Windows)              |  |
|  | - UI Layout: Semantic HTML5 DOM (No Virtual DOM overhead)                                   |  |
|  | - Visual Styling: Pure CSS3 Design Tokens & Hardware-Accelerated Transforms                  |  |
|  | - Code Editor: Embedded CodeMirror 6 (Virtual Scrolling, Syntax Highlight, Dirty Tracking)   |  |
|  | - Client Logic: Native ES Modules (Recursive Deep Proxy, rAF Batcher, UEC State Machine)   |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 |                                                 |
|                   Native OS IPC Bridge          | Authenticated WebSocket (Token-Guarded)         |
|                   (window.pywebview.api)        | (ws://127.0.0.1:{dynamic_port}/ws?token=xyz)    |
|                                                 v v                                               |
|  +---------------------------------------------------------------------------------------------+  |
|  | [SUBSYSTEM 2: ASYNC GATEWAY & EMBEDDED ENGINE] (Process PID: ~28105 | RAM: ~105 MB)           |  |
|  | - Web Server: Uvicorn ASGI Server on ephemeral port (127.0.0.1:{dynamic_port})             |  |
|  | - Security Guard: Ephemeral Token Validator & Strict Origin Checker                         |  |
|  | - Hardware Telemetry Daemon: NVML / sysfs collector (2-second poll interval)                |  |
|  | - Task & Agent Orchestrator: Multi-step Execution Pipeline, Sandbox & Diff Engine            |  |
|  |                                                                                             |  |
|  |   [IN-PROCESS STORAGE & VECTOR MEMORY]                                                      |  |
|  |   - Storage Engine: SQLite 3 with WAL Mode (Write-Ahead Logging, synchronous=NORMAL)       |  |
|  |   - Vector Engine: sqlite-vec C Extension (HNSW Cosine Similarity, Zero-Docker)             |  |
|  |   - Footprint: ~15 MB RAM, 0 external network ports                                         |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 |                                                 |
|                             Async HTTP Stream   |                                                 |
|                             (http://127.0.0.1:  |                                                 |
|                              11434/api/chat)    |                                                 |
|                                                 v                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | [SUBSYSTEM 3: LOCAL NEURAL BRAIN]                                                           |  |
|  | - Engine: Ollama Local Daemon                                                               |  |
|  | - Model: Qwen 2.5 Coder 7B (Q4_K_M)                                                         |  |
|  | - Accelerator: NVIDIA CUDA 12.x / ROCm                                                      |  |
|  | - VRAM Footprint: ~4.7 GB (Realistic Ollama footprint on RTX 2070 Super 8GB)                |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Low-Level Communication Protocols & Security Wire Formats

### 2.1 Dynamic Port & Authentication Handshake
* **Ephemeral Port:** Python backend launch ke waqt OS se free port leta hai (`sock.bind(('127.0.0.1', 0))`). Hardcoded 8000 use nahi hota.
* **Per-Launch Secret Token:** `token = secrets.token_urlsafe(32)`. 
* **Handshake Rule:** Tamam incoming HTTP requests mein `X-DeskAI-Token: <token>` header aur WebSocket upgrade request mein `?token=<token>` parameter zaroori hota hai.
* **Origin Check:** Server incoming `Origin` header ko verify karta hai. Sirf local origin (`http://127.0.0.1:{dynamic_port}` ya internal WebKit scheme) allowed hai; browser tabs ki requests foran HTTP 403 / WS 1008 se reject hoti hain.

### 2.2 Channel 1: Native OS Bridge (`window.pywebview.api`)
* **Usage:** Sirf native OS actions ke liye (Folder Dialogs, Window Min/Max/Close, System Clipboard, Notifications).
* **Wire Envelope:**
  ```json
  {
    "success": true,
    "data": { "path": "/mnt/Data/Workspaces/Projects/DeskAI" },
    "error": null,
    "error_code": null
  }
  ```

### 2.3 Channel 2: Authenticated WebSocket (`ws://127.0.0.1:{port}/ws`)
* **Transport:** Ephemeral TCP Socket with token handshake, sequence numbering (`seq`) aur 15s heartbeat.
* **Resync Protocol:** Client disconnect/reconnect hone par `client.resync` bhejta hai with `last_seq`. Backend snapshot frame bhej kar client state foran update karta hai.
* **Wire Formats:**

  1. **Hardware Telemetry Push (`telemetry.update`):**
     ```json
     {
       "type": "telemetry.update",
       "seq": 1042,
       "payload": {
         "gpu": { "name": "NVIDIA RTX 2070 Super", "active": true, "temp_c": 54 },
         "vram": { "used_mb": 4710, "total_mb": 8192, "pct": 57.5 },
         "cpu": { "usage_pct": 14.8, "cores": 16 },
         "ram": { "used_mb": 5820, "total_mb": 32150 }
       }
     }
     ```

  2. **Streaming AI Token Chunk (`agent.chunk`):**
     ```json
     {
       "type": "agent.chunk",
       "seq": 1043,
       "correlation_id": "req-98f2a1",
       "payload": {
         "token": "def authenticate_user",
         "is_final": false
       }
     }
     ```

  3. **Standardized Error Frame (`system.error`):**
     ```json
     {
       "type": "system.error",
       "seq": 1044,
       "correlation_id": "req-98f2a1",
       "payload": {
         "code": "ERR_SANDBOX_PATH_VIOLATION",
         "message": "Attempted write outside workspace boundary.",
         "details": { "target": "/etc/passwd" }
       }
     }
     ```

### 2.4 Channel 3: Local Vector Memory Query (`sqlite-vec`)
* **Transport:** Direct In-Process C-Extension Call (Zero network hop, sub-1ms latency).
* **Vector Search Query:**
  ```sql
  SELECT chunk_id, file_path, content, distance
  FROM code_embeddings
  WHERE embedding MATCH :query_vector
    AND k = 5
  ORDER BY distance;
  ```

---

## 3. End-to-End Bootstrapping Sequence

```
[User / CLI Launch]
    │
    ▼
1. Launch Entry (src/deskai/main.py)
    │
    ├────────► Allocate Ephemeral Port & Generate Session Secret (32 bytes)
    │
    ├────────► Initialize SQLite Database (WAL mode) & Load sqlite-vec extension
    │          └─ Tables verified: sessions, checkpoints, embeddings (0 Docker)
    │
    ├────────► Async Health-Check for Local Ollama Daemon (http://127.0.0.1:11434)
    │          └─ Non-blocking check; UI displays offline warning if absent
    │
    ├────────► Start FastAPI/Uvicorn on Background Thread
    │          └─ Listening on 127.0.0.1:{dynamic_port} with CSP & Token validation
    │
    └────────► Create PyWebView WebKit Window on Main Thread
               │
               ▼
         WebKit Window Loads http://127.0.0.1:{dynamic_port}/?token=XYZ
               │
               ▼
         DOM Ready & Strict CSP Header enforced
               │
               ▼
         WebSocket Handshake Established with Auth Token
               │
               ▼
         DeskAI Ready (Time to Interactive: ~0.35s)
```

---

## 4. Hardware Resource & Memory Footprint Budget

| Component | Technology | Target Memory | Real-World Overhead |
|---|---|---|---|
| **Window & UI** | PyWebView + WebKitGTK / WebView2 | **~140 MB RAM** | Web process + network process combined |
| **Backend Engine** | Python 3.10 + FastAPI + Uvicorn | **~105 MB RAM** | ASGI event loop + route handlers |
| **Storage & Vectors**| Embedded SQLite (WAL) + sqlite-vec | **~15 MB RAM** | Zero Docker, in-process C-level memory |
| **Local AI Engine** | Ollama (Qwen 2.5 Coder 7B Q4_K_M) | **~4.7 GB VRAM** | RTX 2070 Super (8GB) par ~3.3 GB free |
| **Total Stack** | **DeskAI Complete Suite** | **~260 MB RAM + 4.7 GB VRAM** | Extremely lean, reliable & 100% private |

---

## 5. Lifecycle, Safety & Error Recovery

1. **Window Close & Teardown Rule:**
   - User close request par `closing` hook sirf confirmation check karta hai (`isDirty` tabs check).
   - Tamam irreversible teardown (database commit, temporary sandbox cleanup, process kill) PyWebView ke **`closed`** event mein run hoti hai taake accidental exit par data corrupt na ho.
2. **Terminal Sandbox Enforcement:**
   - Agent ke terminal commands strict working directory (`/mnt/Data/Workspaces/Projects/DeskAI`) ke andar bound rehte hain.
   - 30-second execution timeout aur 1MB max stdout buffer limit enforce hoti hai.
   - High-risk commands (e.g. `rm`, file deletion, external network access) ke liye human-in-the-loop approval card (UEC) lazmi hota hai.
3. **NVIDIA / WebKitGTK Stability on Linux:**
   - WebKitGTK blank window issue se bachne ke liye `WEBKIT_DISABLE_DMABUF_RENDERER=1` auto-configured hota hai.
