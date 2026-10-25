# DeskAI — Technologies Architecture (HLD)

Yeh document **DeskAI** (Autonomous Desktop AI Studio) ke core technologies architecture, subsystem responsibilities, security posture aur lean design principles ki mukammal **High-Level Design (HLD)** specifications **Roman Urdu** mein faraham karta hai.

---

## 1. Client-Side Layer (Desktop Presentation & UI)
* **Core Technologies:** `PyWebView`, `HTML5 (Semantic DOM)`, `CSS3 (Design Tokens)`, `Vanilla JavaScript (ES2022 Modules)`, `CodeMirror 6 (Embedded Editor)`
* **Bunyadi Kirdaar:** Ultra-Lightweight, Secure Desktop IDE & Interaction Shell
* **Tafseel:**
  * **No Heavy Framework:** Electron, React, ya Angular ke baghair native WebKitGTK (Linux) / WebView2 (Windows) engine par direct load hota hai taake system RAM aur battery kharch na ho.
  * **CodeMirror 6 Integration:** Hand-rolled contenteditable editor ke bajaye modular, zero-overhead CodeMirror 6 engine embed kiya gaya hai jo syntax highlighting, virtual scrolling, multi-buffer tabs aur dirty state tracking provide karta hai.
  * **Strict Layout Containment:** CSS `contain: layout paint` aur hardware-accelerated transforms ke zariye 60 FPS UI rendering ensure hoti hai, chahe AI 80+ tokens/sec stream kar raha ho.
  * **DOMPurify Sanitization:** LLM ke generate kardah kisi bhi markdown ya code preview ko DOM mein insert karne se pehle DOMPurify se sanitize kiya jata hai taake XSS attack ka khatra 0% ho jaye.

---

## 2. Server-Side Gateway & IPC Layer (Communication & Security Engine)
* **Core Technologies:** `Python 3.10+`, `FastAPI / Starlette`, `Uvicorn ASGI`, `Secure WebSockets`
* **Bunyadi Kirdaar:** Authenticated Asynchronous Event Gateway & Native Bridge
* **Tafseel:**
  * **Dynamic Ephemeral Port:** Hardcoded port (8000) ke bajaye application launch par OS se free random port (`127.0.0.1:{dynamic_port}`) allocate hota hai.
  * **Cryptographic Session Token:** Launch ke waqt Python `secrets.token_urlsafe(32)` generate karta hai jo frontend ko pass hota hai. Har HTTP request aur WebSocket connection par `X-DeskAI-Token` handshake verify hota hai.
  * **Strict Origin & DNS Rebinding Defense:** Gateway sirf local origin (`http://127.0.0.1:{port}` ya WebKit internal origin) se connections accept karta hai. Kisi aam web browser tab se aane wale connection ko foran drop kiya jata hai.
  * **Strict Content-Security-Policy (CSP):** HTTP response headers ke zariye strict CSP enforce hoti hai (`default-src 'self'; script-src 'self'; connect-src 'self' ws://127.0.0.1:*`), jis se unauthorized external scripts block rehti hain.
  * **Clean Transport Split:** Native OS dialogs (file/folder pickers, window controls) direct `window.pywebview.api` se chalti hain, jabke high-speed data streams (AI tokens, telemetry, terminal I/O) authenticated WebSocket se flow karti hain.
  * **Subprocess Isolation:** Heavy tasks (jaise local embedding generation ya AST chunking) separate Python worker process mein run hoti hain taake main GTK event loop aur UI kabhi freeze na ho.

---

## 3. Local AI Engine (Inference Runtime)
* **Core Technologies:** `Ollama Local Daemon`, `Qwen 2.5 Coder 7B (Q4_K_M)`, `CUDA 12.x / ROCm`
* **Bunyadi Kirdaar:** 100% Private, Hardware-Accelerated Local Intelligence
* **Tafseel:**
  * Machine ke andar 100% offline chalne wala open-weights coding LLM model.
  * NVIDIA RTX 2070 Super (8GB VRAM) par GPU offload hota hai.
  * **Realistic VRAM Budget:** Qwen 2.5 Coder 7B model taqreeban **4.7 GB VRAM** occupy karta hai (na ke 2.1 GB). 8.0 GB card mein se **~3.3 GB free headroom** rehta hai jo OS display aur local embedding models ke liye kaafi hai.
  * Developer ka koi bhi code, prompt ya workspace context internet par kisi teesri company ke paas nahi jata.

---

## 4. Database & State Layer (Embedded Vector & Metadata Store)
* **Core Technologies:** `SQLite 3 (WAL Mode)`, `sqlite-vec Extension`
* **Bunyadi Kirdaar:** Zero-Docker, Zero-Network Embedded Knowledge & Vector Memory
* **Tafseel:**
  * **No Heavy Docker / Postgres:** DeskAI mein Docker container aur external PostgreSQL server ko mukammal khatam kar diya gaya hai.
  * **In-Process Embedded SQLite:** `journal_mode=WAL` (Write-Ahead Logging) aur `synchronous=NORMAL` ke sath high concurrency support karta hai.
  * **Native Vector Search (`sqlite-vec`):** Workspace code chunks ki high-dimensional embeddings ko C-extension `sqlite-vec` ke zariye direct SQLite table mein store aur cosine similarity search kiya jata hai.
  * **Minimal Footprint:** SQLite + sqlite-vec sirf **~15 MB RAM** leti hai aur 0 external TCP ports use karti hai.
  * **Authoritative Source of Truth:** Tamam sessions, task checklists, execution history aur workspace settings backend SQLite database mein persist hoti hain. Frontend reload ya reconnect hone par backend se state snapshot resync ho jati hai.

---

## 5. Subsystem Summary & Architectural Matrix

| Layer | Subsystem | Technology | Runtime Memory | Security & Isolation |
|---|---|---|---|---|
| **Presentation** | Desktop Window & UI | PyWebView + HTML5/CSS3 + CodeMirror 6 | ~120 - 180 MB RAM | CSP Headers, DOMPurify, Frameless/Native Controls |
| **Gateway** | Event Bus & IPC | FastAPI + Uvicorn + Secure WS | ~90 - 110 MB RAM | Dynamic Port, Per-Session Secret Token, Path Sandboxing |
| **Storage & Memory** | Embedded Knowledge Store | SQLite (WAL) + sqlite-vec | ~15 MB RAM | In-process, 0 Docker containers, 0 open network ports |
| **Local AI Engine** | Neural Inference | Ollama (Qwen 2.5 Coder 7B) | ~4.7 GB VRAM | 100% Offline, Localhost API |
| **Total Stack** | **DeskAI Complete Suite** | **Integrated Desktop Studio** | **~250 MB RAM + 4.7 GB VRAM** | Enterprise-grade local security & resilience |

---

## 6. Architectural Rules for DeskAI Development
1. **Never Reintroduce Docker for Local State:** DeskAI ka standard database SQLite aur `sqlite-vec` hi rahega.
2. **Never Expose Unauthenticated Sockets:** Har IPC channel token-guarded aur localhost-bound hona chahiye.
3. **Keep Backend Authoritative:** UI sirf view layer hai; critical business state, rollback history aur checklists database mein honge.
4. **Resilient Offline UX:** Agar Ollama ya GPU na ho, to system graceful warning show karega aur CPU mode / external fallback option dega.
