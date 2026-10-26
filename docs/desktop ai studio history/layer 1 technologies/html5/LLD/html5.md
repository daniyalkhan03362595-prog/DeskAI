# Layer 1 Technology LLD: HTML5 Semantic DOM, Component Layout & Template Engine

Yeh document **DeskAI** ke **Layer 1 (Presentation & Layout)** mein use hone wali **Semantic HTML5** specifications, master DOM tree, CSP-compliant structure, CodeMirror 6 host, aur reusable templates ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka frontend pure **Semantic HTML5** par mushtamil hai jo strict CSP constraints ke mutabiq design kiya gaya hai:

### Low-Level Technical Constraints:
1. **Zero Inline Styles:** CSP violations se bachne ke liye koi inline `style="..."` attribute use nahi hota. Tamam dimensions CSS classes aur CSS variables se handle hoti hain.
2. **Synchronized Action Attributes:** Tamam clickable elements `data-action` attribute use karte hain jo JavaScript event delegation router ke sath 100% matched hain.
3. **Native Dialog & Templates:** Native `<dialog>` element aur non-rendered `<template>` nodes jo DOM rendering cost 0 rakhte hain.
4. **CodeMirror 6 Container:** Hand-rolled contenteditable ke bajaye clean mounting node `<div class="codemirror-host" id="codeEditorHost"></div>`.

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
</head>
<body>
  <div class="app-root" id="appRoot">
    
    <!-- 1. Top Navigation & Window Control Bar -->
    <header class="app-header" id="appHeader">
      <div class="header-left">
        <span class="app-logo">⚡ DeskAI</span>
        <span class="workspace-pill" id="headerWorkspacePill">DeskAI / main</span>
      </div>
      <div class="header-center">
        <button class="omnibar-trigger" id="omnibarBtn" data-action="open-palette" aria-label="Open Command Palette">
          <span class="search-icon">🔍</span>
          <span class="placeholder-text">Search files, symbols, commands... (Ctrl+P)</span>
        </button>
      </div>
      <div class="header-right window-controls">
        <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
        <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
        <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
      </div>
    </header>

    <!-- 2. Main 3-Column IDE Body -->
    <main class="app-body" id="appBody">
      
      <!-- Left Column: File Explorer & Hardware Dock -->
      <aside class="sidebar-left" id="sidebarLeft">
        <nav class="activity-bar" aria-label="Primary Navigation">
          <button class="activity-btn active" data-action="switch-panel" data-panel="explorer" title="Explorer (Ctrl+Shift+E)">📁</button>
          <button class="activity-btn" data-action="switch-panel" data-panel="search" title="Search (Ctrl+Shift+F)">🔍</button>
          <button class="activity-btn" data-action="switch-panel" data-panel="git" title="Source Control">🌿</button>
        </nav>

        <section class="explorer-container">
          <div class="panel-header">
            <span class="panel-title">EXPLORER</span>
            <div class="panel-actions">
              <button class="icon-btn" data-action="new-file" title="New File">📄+</button>
              <button class="icon-btn" data-action="new-folder" title="New Folder">📁+</button>
              <button class="icon-btn" data-action="refresh-tree" title="Refresh">🔄</button>
            </div>
          </div>
          <div class="tree-viewport" id="fileTreeViewport" role="tree" tabindex="0">
            <!-- Dynamic File Tree Rendered Here -->
          </div>
        </section>

        <!-- Hardware Status Dock -->
        <footer class="hardware-dock" id="hardwareDock" aria-label="System Hardware Telemetry">
          <div class="telemetry-row">
            <span class="tele-label">GPU Acceleration</span>
            <span class="tele-badge gpu-badge" id="teleGpuBadge">🟢 RTX 2070 Super</span>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">VRAM Resident</span>
            <span class="tele-val" id="teleVramText">4.7 / 8.0 GB (58%)</span>
          </div>
          <div class="vram-meter-track" role="progressbar" aria-valuenow="58" aria-valuemin="0" aria-valuemax="100">
            <div class="vram-meter-fill" id="teleVramFill"></div>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">Neural Engine</span>
            <span class="tele-val brain-val" id="teleModelName">Qwen 2.5 Coder 7B</span>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">Host RAM</span>
            <span class="tele-val ram-val" id="teleRamText">5.8 / 32.0 GB (18%)</span>
          </div>
        </footer>
      </aside>

      <!-- Resizer Handle Left -->
      <div class="resizer-col" id="resizerLeft" role="separator" aria-orientation="vertical" tabindex="0"></div>

      <!-- Center Column: Multi-tab Code Stage with CodeMirror 6 -->
      <section class="editor-stage" id="editorStage">
        <div class="tab-strip" id="editorTabStrip" role="tablist">
          <!-- Dynamic Tabs Rendered Here -->
        </div>

        <div class="editor-viewport" id="editorViewport">
          <!-- CodeMirror 6 Mount Node -->
          <div class="codemirror-host" id="codeEditorHost"></div>
        </div>

        <!-- Collapsible Bottom Drawer -->
        <section class="bottom-drawer" id="bottomDrawer">
          <div class="drawer-header">
            <div class="drawer-tabs">
              <button class="drawer-tab active" data-action="drawer-tab" data-target="terminal">Terminal</button>
              <button class="drawer-tab" data-action="drawer-tab" data-target="output">Output</button>
              <button class="drawer-tab" data-action="drawer-tab" data-target="problems">Problems</button>
            </div>
            <button class="icon-btn close-drawer-btn" data-action="toggle-drawer">─</button>
          </div>
          <div class="drawer-content" id="drawerContent">
            <pre class="terminal-view" id="terminalOutput"><code>DeskAI Sandboxed Terminal Ready. Bound to workspace root.</code></pre>
          </div>
        </section>
      </section>

      <!-- Resizer Handle Right -->
      <div class="resizer-col" id="resizerRight" role="separator" aria-orientation="vertical" tabindex="0"></div>

      <!-- Right Column: Agentic Chat & Morphing UEC Dock -->
      <aside class="sidebar-right" id="sidebarRight">
        <div class="chat-header">
          <span class="chat-title">AI PAIR PROGRAMMER</span>
          <span class="model-pill">Qwen 2.5 Coder 7B</span>
        </div>

        <div class="chat-thread" id="chatThread" role="log" aria-live="polite">
          <!-- DOMPurify-Sanitized Chat Bubbles Rendered Here -->
        </div>

        <!-- Unified Execution Card (UEC) Container -->
        <div class="uec-container" id="uecContainer" aria-label="Autonomous Execution Task">
          <!-- UEC Morphing State Rendered Here -->
        </div>

        <!-- Prompt Input Dock -->
        <form class="prompt-dock" id="promptForm">
          <div class="prompt-input-wrapper">
            <textarea id="promptTextarea" class="prompt-textarea" rows="1" placeholder="Instruct AI to code, refactor or debug... (Ctrl+Enter to send)"></textarea>
            <button type="submit" class="prompt-send-btn" id="promptSendBtn" title="Send Prompt">➔</button>
          </div>
        </form>
      </aside>

    </main>

    <!-- 3. Native Dialogs & Modals -->
    <dialog class="palette-dialog" id="commandPaletteDialog" aria-label="Command Palette">
      <div class="palette-search-box">
        <span class="palette-icon">🔍</span>
        <input type="text" id="paletteSearchInput" class="palette-input" placeholder="Type a command or search files..." autofocus>
      </div>
      <ul class="palette-list" id="paletteResultsList" role="listbox">
        <!-- Filtered commands rendered here -->
      </ul>
    </dialog>

    <div class="toast-rack" id="toastRack" aria-live="assertive"></div>

    <!-- 4. Reusable HTML5 Component Templates -->
    <div id="templateStore" hidden aria-hidden="true">
      
      <!-- Template: Tree Node -->
      <template id="tplTreeNode">
        <li class="tree-item" role="treeitem" data-path="" data-kind="">
          <span class="tree-chevron">▶</span>
          <span class="tree-icon">📄</span>
          <span class="tree-label">filename.py</span>
          <span class="tree-dirty-dot"></span>
        </li>
      </template>

      <!-- Template: Editor Tab (Action: tab-close) -->
      <template id="tplEditorTab">
        <div class="editor-tab" role="tab" data-tab-id="" data-path="" tabindex="0">
          <span class="tab-icon">📄</span>
          <span class="tab-label">file.py</span>
          <span class="tab-dirty-indicator">●</span>
          <button class="tab-close-btn" data-action="tab-close" aria-label="Close Tab">✕</button>
        </div>
      </template>

      <!-- Template: Chat Bubble (Sanitized Markdown Body) -->
      <template id="tplChatBubble">
        <article class="chat-bubble" data-role="">
          <div class="bubble-header">
            <span class="bubble-author">User</span>
            <time class="bubble-time">12:30 PM</time>
          </div>
          <div class="bubble-body markdown-surface"></div>
        </article>
      </template>

      <!-- Template: UEC Card with Approve, Reject, Rollback & Cancel Actions -->
      <template id="tplUecCard">
        <div class="uec-card" data-state="PLANNING">
          <div class="uec-header">
            <span class="uec-phase-badge">PLANNING</span>
            <span class="uec-task-title">Refactor Auth Service</span>
          </div>
          <ul class="uec-checklist" id="uecChecklist"></ul>
          <div class="uec-actions">
            <button class="uec-btn btn-cancel" data-action="uec-cancel">Cancel</button>
            <button class="uec-btn btn-reject" data-action="uec-reject">Reject</button>
            <button class="uec-btn btn-rollback" data-action="uec-rollback">Rollback</button>
            <button class="uec-btn btn-approve" data-action="uec-approve">Approve & Execute</button>
          </div>
        </div>
      </template>

    </div>

  </div>
  <script type="module" src="js/app.js"></script>
</body>
</html>
```
