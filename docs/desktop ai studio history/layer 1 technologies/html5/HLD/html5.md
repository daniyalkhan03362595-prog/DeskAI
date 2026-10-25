# Layer 1 Technology HLD: HTML5 DOM & Layout Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Layout)** mein use hone wali **Semantic HTML5** ki mukammal **High-Level Design (HLD)** architecture aur component hierarchy ko **Roman Urdu** mein bayan karta hai.

---

## 1. Executive Summary (Bunyadi Falsafa)
DeskAI mein heavy client-side frameworks ke bajaye **Semantic HTML5 DOM** approach istemal ki gayi hai.

### Is Strategy ke Fawaid:
1. **Zero Framework Overhead:** Virtual DOM diffing ya heavy JavaScript bundle parsing ka koi bojh nahi hai.
2. **Instant Window Launch:** App launch hote hi bina kisi delay ke render hoti hai.
3. **Clean CodeMirror 6 Mount:** Semantic container layout jo modern CodeMirror 6 editor aur hardware dock ko seamlessly nest karta hai.
4. **Low Memory Footprint:** WebKit engine par memory ka dabao kam se kam rehta hai (~140MB total UI RAM).

---

## 2. Master DOM Hierarchy (`<div class="app-root">`)

Application interface chaar baray semantic hisson mein taqseem hai:

```text
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- Strict Content Security Policy enforced via HTTP headers -->
    <title>DeskAI Studio</title>
    <link rel="stylesheet" href="css/tokens.css">
    <link rel="stylesheet" href="css/layout.css">
    <link rel="stylesheet" href="css/components.css">
  </head>
  <body>
    <div class="app-root" id="appRoot">
      
      <!-- 1. Top Control Bar -->
      <header class="app-header" id="appHeader"> ... </header>

      <!-- 2. Main 3-Column Layout -->
      <main class="app-body" id="appBody">
        
        <!-- Left Column: File Tree & Hardware Status -->
        <aside class="sidebar-left" id="sidebarLeft">
          <nav class="activity-bar"> ... </nav>
          <div class="file-tree" id="fileTreeViewport"> ... </div>
          <footer class="hardware-dock" id="hardwareDock"> ... </footer>
        </aside>

        <!-- Resizer Handle Left -->
        <div class="resizer-col" id="resizerLeft" role="separator"></div>

        <!-- Center Column: Multi-tab Code Stage -->
        <section class="editor-stage" id="editorStage">
          <div class="tab-strip" id="editorTabStrip"> ... </div>
          <div class="editor-viewport" id="editorViewport">
            <!-- CodeMirror 6 Container Mounted Here -->
            <div class="codemirror-host" id="codeEditorHost"></div>
          </div>
          <section class="bottom-drawer" id="bottomDrawer"> ... </section>
        </section>

        <!-- Resizer Handle Right -->
        <div class="resizer-col" id="resizerRight" role="separator"></div>

        <!-- Right Column: Agentic Chat & Morphing UEC Card -->
        <aside class="sidebar-right" id="sidebarRight">
          <div class="chat-thread" id="chatThread"> ... </div>
          <div class="uec-container" id="uecContainer"> ... </div>
          <form class="prompt-dock" id="promptForm"> ... </form>
        </aside>

      </main>

      <!-- 3. Modal & Overlay Layer -->
      <dialog id="commandPaletteDialog" class="palette-dialog"> ... </dialog>
      <div id="toastRack" class="toast-rack" aria-live="assertive"></div>

    </div>
  </body>
</html>
```

---

## 3. Char Bunyadi HLD Zones ki Tafseel

### Zone 1: Left Dock (`<aside class="sidebar-left">`)
* **Activity Bar:** Workspace switch karne, global search aur source control ke navigation controls.
* **File Explorer Tree (`#fileTreeViewport`):** Nested files aur folders ko clean tree structure mein display karta hai.
* **Hardware Status Footer (`#hardwareDock`):** Screen ke bottom par fixed telemetry status card:
  1. `GPU Acceleration`: 🟢 NVIDIA RTX 2070 Super status badge.
  2. `VRAM Resident`: Usage counter (`4.7 / 8.0 GB`) + `<div class="vram-meter-track">` visual fill bar.
  3. `Local Neural Brain`: Offline coding LLM (`Qwen 2.5 Coder 7B`).
  4. `Embedded Vector DB`: In-process vector store (`SQLite 3 WAL + sqlite-vec`).

### Zone 2: Central Code Stage (`<section class="editor-stage">`)
* **Tab Strip (`#editorTabStrip`):** Multi-file tabs with dirty state dots aur close action (`tab-close`).
* **CodeMirror 6 Editor Host (`#codeEditorHost`):** Virtualized scrolling, real-time syntax highlighting aur clean DOM structure.
* **Bottom Drawer (`#bottomDrawer`):** Collapsible panel for sandboxed terminal output and diagnostic logs.
* **Resizer Handles (`.resizer-col`):** Dual split-pane dragging support.

### Zone 3: Right Sidebar (`<aside class="sidebar-right">`)
* **Chat Thread (`#chatThread`):** User prompts aur DOMPurify-sanitized AI streaming markdown surfaces.
* **Unified Execution Card (UEC) (`#uecContainer`):** In-place morphing component jo checklist steps, diff acceptance, rollback aur cancellation handle karta hai.

### Zone 4: Native Modal & Dialog Layer (`<dialog>`)
* **Command Palette (`#commandPaletteDialog`):** Native HTML5 `<dialog>` element jo zero library overhead ke sath `Ctrl + P` par activate hota hai.
* **Toast Rack (`#toastRack`):** Temporary asynchronous warning aur status pills.
