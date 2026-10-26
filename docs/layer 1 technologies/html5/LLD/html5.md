# Layer 1 Technology LLD: HTML5 Semantic DOM, Component Layout & Template Engine

Yeh document **DeskAI** ke **Layer 1 (Presentation & Layout)** mein use hone wali **Semantic HTML5** specifications, master DOM tree, CSP-compliant structure, vendor scripts loading, ARIA accessibility attributes, CodeMirror 6 host, aur reusable templates ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka frontend pure **Semantic HTML5** par mushtamil hai jo strict CSP aur WCAG accessibility constraints ke mutabiq design kiya gaya hai:

### Low-Level Technical Constraints:
1. **Explicit Vendor Loading:** Vendor singletons (`DOMPurify`, `marked`, `CodeMirror 6`) module scripts se pehle synchronously load hotay hain taake execution ke waqt `ReferenceError` na aaye.
2. **Accessible Screen Reader Announcement:** Rapid streaming container se `aria-live` hata kar dedicated announcer element banaya gaya hai jo sirf stream complete hone par polite announce karta hai.
3. **Complete Action Coverage:** Master DOM aur UEC buttons ke tamam 16 actions `data-action` attribute use karte hain jo JavaScript event router ke sath 100% synchronized hain.
4. **Full ARIA Hierarchy:** Native `tablist`, `tab`, `tabpanel`, `tree`, aur `treeitem` with dynamic `aria-selected` aur `aria-expanded`.

---

## 2. Master DOM Specification (`index.html`)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="ie=edge">
  <title>DeskAI Studio</title>
  <link rel="stylesheet" href="css/tokens.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/components.css">

  <!-- 1. Vendor Singletons (Synchronous Loading Before Modules) -->
  <script src="vendor/purify.min.js"></script>
  <script src="vendor/marked.min.js"></script>
  <script src="vendor/codemirror.bundle.js"></script>
</head>
<body>
  <div class="app-root" id="appRoot">
    
    <!-- 2. Top Navigation & Window Control Bar -->
    <header class="app-header" id="appHeader" role="banner">
      <div class="header-left">
        <span class="app-logo">⚡ DeskAI</span>
        <span class="workspace-pill" id="headerWorkspacePill">DeskAI / main</span>
      </div>
      <div class="header-right window-controls" role="group" aria-label="Window Controls">
        <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
        <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
        <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
      </div>
    </header>

    <!-- 3. Main 3-Column IDE Body -->
    <main class="app-body" id="appBody" role="main">
      
      <!-- Left Column: File Explorer & Hardware Dock -->
      <aside class="sidebar-left" id="sidebarLeft" role="region" aria-label="Explorer & System Dock">
        <section class="explorer-container">
          <div class="panel-header">
            <span class="panel-title">EXPLORER</span>
            <div class="panel-actions" role="toolbar" aria-label="Explorer Actions">
              <button class="icon-btn" data-action="new-file" title="New File" aria-label="New File">📄+</button>
              <button class="icon-btn" data-action="new-folder" title="New Folder" aria-label="New Folder">📁+</button>
              <button class="icon-btn" data-action="refresh-tree" title="Refresh Tree" aria-label="Refresh Tree">🔄</button>
            </div>
          </div>
          <div class="tree-viewport" id="fileTreeViewport" role="tree" tabindex="0" aria-label="Project Files">
            <!-- Dynamic File Tree Rendered Here -->
          </div>
        </section>

        <!-- Hardware Status Dock -->
        <footer class="hardware-dock" id="hardwareDock" role="contentinfo" aria-label="Host System Telemetry">
          <div class="telemetry-row">
            <span class="tele-label">GPU Acceleration</span>
            <span class="tele-badge gpu-badge" id="teleGpuBadge">🟢 Detecting...</span>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">VRAM Resident</span>
            <span class="tele-val" id="teleVramText">-- / -- GB</span>
          </div>
          <div class="vram-meter-track" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
            <div class="vram-meter-fill" id="teleVramFill"></div>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">Host RAM</span>
            <span class="tele-val ram-val" id="teleRamText">-- / -- GB</span>
          </div>
        </footer>
      </aside>

      <!-- Resizer Handle Left -->
      <div class="resizer-col" id="resizerLeft" role="separator" aria-orientation="vertical" tabindex="0" aria-label="Resize Explorer"></div>

      <!-- Center Column: Multi-tab Code Stage with CodeMirror 6 -->
      <section class="editor-stage" id="editorStage" role="region" aria-label="Code Editor Stage">
        <div class="tab-strip" id="editorTabStrip" role="tablist" aria-label="Open Files">
          <!-- Dynamic Tabs Rendered Here with role="tab" & aria-selected -->
        </div>

        <div class="editor-viewport" id="editorViewport" role="tabpanel" aria-label="Active File Editor">
          <div class="welcome-screen" id="welcomeScreen">
            <h2>Welcome to DeskAI</h2>
            <p>Select a project folder to begin.</p>
            <button class="primary-btn" data-action="open-folder-dialog">Open Project Folder</button>
          </div>
          <!-- CodeMirror 6 Mount Node -->
          <div class="codemirror-host" id="codeEditorHost" role="region" aria-label="Code Surface"></div>
        </div>

        <!-- Collapsible Bottom Drawer -->
        <section class="bottom-drawer" id="bottomDrawer" role="region" aria-label="Output Drawer">
          <div class="drawer-header">
            <div class="drawer-tabs" role="tablist" aria-label="Drawer Panels">
              <button class="drawer-tab active" data-action="drawer-tab" data-target="terminal" role="tab" aria-selected="true">Terminal</button>
              <button class="drawer-tab" data-action="drawer-tab" data-target="output" role="tab" aria-selected="false">Output</button>
              <button class="drawer-tab" data-action="drawer-tab" data-target="problems" role="tab" aria-selected="false">Problems</button>
            </div>
            <button class="icon-btn close-drawer-btn" data-action="toggle-drawer" aria-label="Toggle Drawer">─</button>
          </div>
          <div class="drawer-content" id="drawerContent">
            <pre class="terminal-view" id="terminalOutput"><code>DeskAI Host Shell Ready. Workspace active.</code></pre>
          </div>
        </section>
      </section>

      <!-- Resizer Handle Right -->
      <div class="resizer-col" id="resizerRight" role="separator" aria-orientation="vertical" tabindex="0" aria-label="Resize Chat Sidebar"></div>

      <!-- Right Column: Agentic Chat & Morphing UEC Dock -->
      <aside class="sidebar-right" id="sidebarRight" role="region" aria-label="AI Interaction Panel">
        <div class="chat-header">
          <span class="chat-title">AI ASSISTANT</span>
          <span class="model-pill" id="headerModelPill">Ready</span>
        </div>

        <!-- Rapid streaming container (without aria-live to prevent reader spam) -->
        <div class="chat-thread" id="chatThread" role="log" aria-label="Chat Message History">
          <!-- DOMPurify-Sanitized Chat Bubbles Rendered Here -->
        </div>

        <!-- Unified Execution Card (UEC) Container -->
        <div class="uec-container" id="uecContainer" role="region" aria-label="Autonomous Task Execution Card">
          <!-- Dynamic UEC State & Buttons Rendered Here -->
        </div>

        <!-- Prompt Input Dock -->
        <form class="prompt-dock" id="promptForm" role="form" aria-label="Prompt Input">
          <div class="prompt-input-wrapper">
            <textarea id="promptTextarea" class="prompt-textarea" rows="1" placeholder="Instruct AI to code, refactor or debug... (Ctrl+Enter to send)" aria-label="AI Prompt"></textarea>
            <button type="submit" class="prompt-send-btn" id="promptSendBtn" title="Send Prompt" aria-label="Send">➔</button>
          </div>
        </form>
      </aside>

    </main>

    <!-- 4. Accessible Announcements & Toast Rack -->
    <div id="screenReaderAnnouncer" class="sr-only" aria-live="polite" aria-atomic="true"></div>
    <div class="toast-rack" id="toastRack" aria-live="assertive" role="alert"></div>

    <!-- 6. Reusable HTML5 Component Templates -->
    <div id="templateStore" hidden aria-hidden="true">
      
      <!-- Template: Tree Item -->
      <template id="tplTreeNode">
        <li class="tree-item" role="treeitem" data-path="" data-kind="" aria-expanded="false" tabindex="-1">
          <span class="tree-chevron">▶</span>
          <span class="tree-icon">📄</span>
          <span class="tree-label">filename.py</span>
          <span class="tree-dirty-dot"></span>
        </li>
      </template>

      <!-- Template: Editor Tab -->
      <template id="tplEditorTab">
        <div class="editor-tab" role="tab" data-tab-id="" data-path="" tabindex="0" aria-selected="false" data-action="select-tab">
          <span class="tab-icon">📄</span>
          <span class="tab-label">file.py</span>
          <span class="tab-dirty-indicator">●</span>
          <button class="tab-close-btn" data-action="tab-close" aria-label="Close Tab">✕</button>
        </div>
      </template>

      <!-- Template: Chat Bubble -->
      <template id="tplChatBubble">
        <article class="chat-bubble" data-role="">
          <div class="bubble-header">
            <span class="bubble-author">User</span>
            <time class="bubble-time">12:30 PM</time>
          </div>
          <div class="bubble-body markdown-surface"></div>
        </article>
      </template>

      <!-- Template: UEC Card -->
      <template id="tplUecCard">
        <div class="uec-card" data-state="PLANNING">
          <div class="uec-header">
            <span class="uec-phase-badge">PLANNING</span>
            <span class="uec-task-title">Refactor Auth Service</span>
          </div>
          <ul class="uec-checklist" id="uecChecklist"></ul>
          <div class="uec-actions">
            <!-- Dynamic State-Driven Buttons Rendered by UECStateMachine -->
          </div>
        </div>
      </template>

    </div>

  </div>
  <!-- Application Entrypoint Module -->
  <script type="module" src="js/app.js"></script>
</body>
</html>
```
