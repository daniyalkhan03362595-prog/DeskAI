# Desktop AI Studio — Technologies Architecture (HLD)

Yeh document **Desktop AI Studio** ke purane tamam technologies architecture ki mukammal tafseel **Roman Urdu** mein faraham karta hai.

---

## 1. Client-Side Layer (Frontend & UI)
* **Technologies:** `HTML5`, `CSS3`, `Vanilla JavaScript`, `PyWebView`
* **Bunyadi Kirdaar:** Single-Page Lightweight Desktop IDE Window
* **Tafseel:**
  * Baghair kisi heavy framework (jaise React, Angular ya Electron) ke direct lightweight DOM par bani thi.
  * PyWebView ke zariye native OS window mein load hoti thi taake system memory (RAM) aur battery kam kharch ho.
  * Code Editor, Multi-tabs, Agentic Chat stream, aur Hardware Status Footer ko seamlessly render karti thi.
  * WebSockets ke sath connect ho kar real-time mein AI ke generated tokens screen par render karti thi.

---

## 2. Server-Side Layer (Backend & Communication Hub)
* **Technologies:** `Python 3.10+`, `FastAPI`, `Starlette`, `Uvicorn`, `WebSockets`
* **Bunyadi Kirdaar:** Asynchronous Real-Time Event & API Gateway
* **Tafseel:**
  * Frontend UI aur background ke AI/System tools ke darmiyan main pul (bridge) ka kaam karta tha.
  * Uvicorn server par WebSockets ke zariye low-latency 2-way streaming connection banata tha.
  * File read/write, terminal execution, workspace scanning aur security tokens verify karta tha.
  * Hardware telemetry (GPU/VRAM) ka background daemon run karta tha jo har 2 second baad UI ko update bhejta tha.

---

## 3. Local AI Engine (Inference Runtime)
* **Technologies:** `Ollama Local Daemon`, `Qwen 2.5 Coder 7B (Q4_K_M)`, `NVIDIA CUDA Runtime`
* **Bunyadi Kirdaar:** 100% Offline Hardware-Accelerated Intelligence
* **Tafseel:**
  * Machine ke andar 100% offline chalne wala open-weights coding LLM model.
  * NVIDIA RTX 2070 Super GPU ke parallel CUDA cores par run hota tha (CPU ke muqable mein 10x tezi se).
  * Model sirf ~2.1 GB VRAM leta tha, jis se 8.0 GB card mein se ~6.0 GB headroom bilkul free rehta tha.
  * Developer ka koi bhi private code ya prompt internet par kisi teesri company ke paas nahi jata tha.

---

## 4. Database & State Layer (Vector Knowledge Store)
* **Technologies:** `Docker Engine`, `PostgreSQL 17`, `pgvector 0.8.7 Extension`
* **Bunyadi Kirdaar:** High-Dimensional Vector Retrieval & Workspace Memory
* **Tafseel:**
  * Workspace ki tamam project files aur code chunks ko mathematical numbers (vectors) mein save karta tha.
  * HNSW cosine similarity search ke zariye developer ke sawal ka sab se relevant code foran dhoondta tha.
  * Docker container (`orchestrix-test-postgres`) ke andar port 5433 par run hota tha.
  * Session history, chat checkpoints aur agent states ko persistent tables mein store karta tha.

---

## 5. Architectural Lessons & Future DeskAI Strategy
1. **Purane Stack Ki Khubiyan (Strengths):**
   * Single-page vanilla UI super fast thi aur Electron ke muqable mein bohot kam RAM leti thi.
   * Ollama aur RTX 2070 Super ke sath Qwen 7B model local GPU par 100% private aur instant code generate karta tha.
2. **Masle Jin Ki Wajah Se Wipeout Hua (Weaknesses Fixed in DeskAI):**
   * Docker aur PostgreSQL developer machine par zaroorat se zyada heavy aur complex the.
   * Orchestrator, planning agents aur pipelines mein code over-engineering aur rigid ho gaya tha. Ab DeskAI mein bilkul lean, lightweight aur scalable design banegi.
