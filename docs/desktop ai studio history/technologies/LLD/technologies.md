# Desktop AI Studio — Technologies Integration & Subsystem Interoperability (LLD)

Yeh document **Desktop AI Studio** ke tamam technologies (`PyWebView`, `HTML5/CSS3/JS`, `FastAPI/Uvicorn`, `Ollama/Qwen 7B`, `PostgreSQL/pgvector`) ke aapsi **Low-Level Design (LLD)** integration protocols, IPC wire formats, process boundaries, memory budgets aur startup/shutdown lifecycle ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Full-Stack System Topology

Desktop AI Studio ka runtime 4 ahem subsystems par mushtamil tha jo operating system ke andar loopback networking aur C-level shared memory ke zariye aapas mein communicate karte the:

```text
+---------------------------------------------------------------------------------------------------+
|                                      LINUX OS (HOST RUNTIME)                                      |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [SUBSYSTEM 1: DESKTOP CLIENT] (Process PID: ~28100 | RAM: ~65 MB)                           |  |
|  | - Window Shell: PyWebView WebKit2GTK Container (GDK_BACKEND="x11,wayland")                  |  |
|  | - UI Layout: Semantic HTML5 DOM (No Virtual DOM)                                            |  |
|  | - Visual Styling: Pure CSS3 Design Tokens & Hardware-Accelerated Transforms                  |  |
|  | - Client Logic: Pure Vanilla ES Modules (Proxy Store, rAF Token Streamer, UEC State Machine)  |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 |                                                 |
|                        C-Level Memory IPC Bridge| | Local WebSocket Protocol                     |
|                        (window.pywebview.api)   | | (ws://127.0.0.1:8000/ws)                      |
|                                                 v v                                               |
|  +---------------------------------------------------------------------------------------------+  |
|  | [SUBSYSTEM 2: ASYNC GATEWAY & ENGINE] (Process PID: ~28105 | RAM: ~95 MB)                    |  |
|  | - Web Server: Uvicorn ASGI Server (uvloop, httptools)                                       |  |
|  | - Application Framework: FastAPI 0.100+ / Starlette                                          |  |
|  | - Hardware Telemetry Daemon: PyNVML / GPUtil (2-second poll interval)                         |  |
|  | - Task & Agent Orchestrator: Multi-step Execution Pipeline & Diff Engine                     |  |
|  +-----------------------+----------------------------------------------+----------------------+  |
|                          |                                              |                         |
|     Async HTTP Streaming |                                    Connection| Pool (asyncpg)          |
|     (http://127.0.0.1:   |                                    (tcp://127| .0.0.1:5433)            |
|      11434/api/chat)     |                                              |                         |
|                          v                                              v                         |
|  +-----------------------------------+              +------------------------------------------+  |
|  | [SUBSYSTEM 3: LOCAL NEURAL BRAIN] |              | [SUBSYSTEM 4: VECTOR KNOWLEDGE STORE]    |  |
|  | - Engine: Ollama Local Daemon     |              | - Container: Docker Engine               |  |
|  | - Model: Qwen 2.5 Coder 7B Q4_K_M |              | - Engine: PostgreSQL 17                  |  |
|  | - Accelerator: CUDA 12.x          |              | - Vector Plugin: pgvector 0.8.7 (HNSW)   |  |
|  | - VRAM Footprint: ~2.1 GB         |              | - RAM Footprint: ~180 MB                 |  |
|  +-----------------------------------+              +------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Low-Level Communication Protocols & Wire Formats

Charon layers ke darmiyan hone wale data exchange ke exact formats yeh the:

### 2.1 Channel 1: Client ➔ PyWebView Bridge (`window.pywebview.api`)
* **Transport:** WebKit2GTK C-Level Script Messages (Zero network packet overhead).
* **Latency:** < 0.2ms.
* **Request Signature:**
  ```javascript
  const res = await window.pywebview.api.open_directory_dialog("Select Project");
  ```
* **Wire Response Envelope:**
  ```json
  {
    "success": true,
    "data": {
      "path": "/mnt/Data/Workspaces/Projects/DeskAI"
    },
    "error": null,
    "error_code": null
  }
  ```

### 2.2 Channel 2: Client ➔ Gateway WebSocket (`ws://127.0.0.1:8000/ws`)
* **Transport:** Persistent TCP Socket with 15-second heartbeat ping.
* **Multiplexed Action Schemas:**
  1. **Hardware Telemetry Push (`telemetry.update`):**
     ```json
     {
       "type": "telemetry.update",
       "payload": {
         "gpu": { "name": "NVIDIA RTX 2070 Super", "active": true, "temp_c": 54 },
         "vram": { "used_mb": 2150, "total_mb": 8192, "pct": 26.2 },
         "cpu": { "usage_pct": 14.8, "cores": 16 },
         "ram": { "used_mb": 6240, "total_mb": 32150 }
       }
     }
     ```
  2. **Streaming AI Token Chunk (`agent.chunk`):**
     ```json
     {
       "type": "agent.chunk",
       "correlation_id": "req-98f2a1",
       "payload": {
         "token": "def authenticate_user",
         "is_final": false
       }
     }
     ```
  3. **Plan Step Checklist (`agent.plan`):**
     ```json
     {
       "type": "agent.plan",
       "payload": {
         "task_id": "task-01",
         "title": "Implement JWT Middleware",
         "steps": [
           { "index": 0, "desc": "Create auth schema", "status": "COMPLETED" },
           { "index": 1, "desc": "Mount middleware", "status": "IN_PROGRESS" }
         ]
       }
     }
     ```

### 2.3 Channel 3: Gateway ➔ Ollama Daemon (`http://127.0.0.1:11434/api/chat`)
* **Transport:** Asynchronous HTTP/1.1 chunked transfer streaming (`httpx.AsyncClient`).
* **Request Payload:**
  ```json
  {
    "model": "qwen2.5-coder:7b",
    "messages": [
      { "role": "system", "content": "You are DeskAI coding agent..." },
      { "role": "user", "content": "Add unit tests for user login" }
    ],
    "options": {
      "temperature": 0.2,
      "num_ctx": 16384,
      "num_gpu": 33
    },
    "stream": true
  }
  ```
* **Stream Chunk Response:**
  ```json
  {
    "model": "qwen2.5-coder:7b",
    "created_at": "2026-10-26T03:45:00Z",
    "message": { "role": "assistant", "content": "import pytest\n" },
    "done": false
  }
  ```

### 2.4 Channel 4: Gateway ➔ PostgreSQL/pgvector (`127.0.0.1:5433`)
* **Transport:** Binary PostgreSQL wire protocol using `asyncpg` connection pool.
* **HNSW Vector Search Query:**
  ```sql
  SELECT file_path, chunk_index, content, 
         1 - (embedding <=> $1) AS cosine_similarity
  FROM workspace_code_chunks
  WHERE workspace_id = $2
  ORDER BY embedding <=> $1
  LIMIT 5;
  ```

---

## 3. End-to-End Handshake & Startup Sequence

Application launch ke waqt 4 subsystems ka bootstrapping sequence:

```
[User / CLI]
    │
    ▼
1. Launch Python Entry (src/deskai/app.py)
    │
    ├────────► Check Ollama Daemon (http://127.0.0.1:11434/api/tags)
    │          └─ Model Verified: Qwen 2.5 Coder 7B (2.1 GB VRAM ready)
    │
    ├────────► Verify Postgres Container (docker inspect orchestrix-test-postgres)
    │          └─ pgvector 0.8.7 extension verified
    │
    ├────────► Spawn FastAPI / Uvicorn Background Thread (Thread-2)
    │          └─ Listening on http://127.0.0.1:8000
    │
    └────────► Start PyWebView Window on Main Thread (Thread-1)
               │
               ▼
        WebKitGTK Window Created (1440x900)
               │
               ▼
        Loads http://127.0.0.1:8000/static/index.html
               │
               ▼
        DOM Ready & js_api injected
               │
               ▼
        ws.connect() ──► WebSocket Handshake Established (ws://127.0.0.1:8000/ws)
               │
               ▼
        App Fully Operational (Time to Interactive: ~0.35s)
```

---

## 4. Hardware Resource & Memory Footprint Budget

Desktop AI Studio ki sab se bari kamyabi iska nihayat lean memory budget tha:

| Component | Technology | Target Memory | Overhead vs Alternative |
|---|---|---|---|
| **Window & UI** | PyWebView + WebKitGTK | **~65 MB RAM** | Electron (~600 MB) ke muqable mein 90% bachat |
| **Server Engine** | FastAPI + Uvicorn + uvloop | **~95 MB RAM** | Node.js Express/Nest ke muqable mein 40% tez |
| **Database** | PostgreSQL 17 + pgvector | **~180 MB RAM** | Pinecone/Milvus server ke muqable mein 100% local |
| **Neural AI Model** | Qwen 2.5 Coder 7B (Q4_K_M) | **~2.1 GB VRAM** | RTX 2070 Super (8GB) par 6GB headroom bilkul free |
| **Total Stack** | **Entire Desktop Studio** | **~340 MB RAM + 2.1 GB VRAM** | Extreme lightweight & 100% private |

---

## 5. Graceful Teardown & Fault-Tolerance Matrix

System reliability ke liye fail-safe rules:

1. **Window Close Event (`closing`):**
   - Jab user 'X' button dabata hai, PyWebView ka `closing` hook intercept hota hai.
   - Active WebSocket connections ko status code 1000 (Normal Closure) send hota hai.
   - Uvicorn server graceful shutdown trigger karta hai (inflight file writes flush hotay hain).
   - Python main thread `sys.exit(0)` par terminate hota hai (zero zombie background processes).
2. **Ollama Crash Recovery:**
   - Agar local Ollama daemon crash ho jaye, to WebSocket client UI par instant yellow alert pill ("Brain Disconnected") show karta hai aur backend auto-retry loop mein chala jata hai.
3. **Database Unavailability:**
   - Agar PostgreSQL container stop ho jaye, to IDE core features (file editing, syntax highlighting, terminal) bina ruki chalti hain, sirf vector search fallback to direct regex grep search ho jata hai.
