# Layer 1 Technology LLD: HTML5 Semantic DOM, Component Templates & Accessibility

Yeh document **Desktop AI Studio** ke **Layer 1 (Frontend)** mein use hone wali **HTML5** ki mukammal **Low-Level Design (LLD)** specifications, semantic markup hierarchy, component templates, data-attributes routing aur ARIA accessibility standards ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Scope

Desktop AI Studio ka frontend structure kisi virtual DOM library ke bajaye **Semantic HTML5** standards par mabni hai. Yeh browser ke native C++ layout engine (WebKit WebCore) ko direct trigger karta hai, jis se UI rendering latency 0.1ms se kam rehti hai.

### Low-Level Responsibilities:
1. **Deterministic Master Layout:** 3-column desktop IDE structure (Header, Left Sidebar, Editor Stage, Right Agent Dock, Bottom Drawer, Overlay Modals).
2. **HTML5 `<template>` Engine:** High-performance reusable client-side DOM blueprints (Tree nodes, Editor tabs, Chat bubbles, UEC cards).
3. **Data-Attribute Action Dispatching:** Event delegation ke liye standardized `data-action` contracts.
4. **Native Modal & Dialogs:** `<dialog>` element ka native modal loop bina kisi external modal library ke.
5. **Accessibility (ARIA):** Screen readers aur keyboard navigation ke liye complete ARIA role hierarchy.

---

## 2. Master DOM Hierarchy & File Specifications

Primary entry point file `src/deskai/static/index.html` hai:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' ws:;">
  <title>Desktop AI Studio</title>
  <link rel="stylesheet" href="css/tokens.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/components.css">
</head>
<body class="theme-dark">
  <div class="app-root" id="appRoot">

    <!-- 1. Native Header Bar -->
    <header class="app-header" id="appHeader" role="banner">
      <div class="header-left">
        <svg class="app-logo" viewBox="0 0 24 24" width="18" height="18">
          <circle cx="12" cy="12" r="10" fill="#1abc9c"/>
        </svg>
        <span class="app-title">Desktop AI Studio</span>
        <span class="workspace-badge" id="headerWorkspaceName">No Workspace</span>
      </div>
      <div class="header-center">
        <button class="palette-trigger-btn" data-action="open-palette" aria-keyshortcuts="Control+P">
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
      <aside class="sidebar-left" id="sidebarLeft" style="width: var(--sidebar-left-w);">
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

        <!-- Hardware Status Dock (Req 20) -->
        <footer class="hardware-dock" id="hardwareDock" aria-label="System Hardware Telemetry">
          <div class="telemetry-row">
            <span class="tele-label">GPU Acceleration</span>
            <span class="tele-badge gpu-badge" id="teleGpuBadge">🟢 RTX 2070 Super</span>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">VRAM Resident</span>
            <span class="tele-val" id="teleVramText">1.8 / 8.0 GB (22%)</span>
          </div>
          <div class="vram-meter-track" role="progressbar" aria-valuenow="22" aria-valuemin="0" aria-valuemax="100">
            <div class="vram-meter-fill" id="teleVramFill" style="width: 22.5%;"></div>
          </div>
          <div class="telemetry-row">
            <span class="tele-label">Neural Model</span>
            <span class="tele-val brain-val" id="teleModelName">Qwen 2.5 Coder 7B</span>
          </div>
        </footer>
      </aside>

      <!-- Resizer Handle Left -->
      <div class="resizer-col" id="resizerLeft" role="separator" aria-orientation="vertical" tabindex="0"></div>

      <!-- Center Column: Multi-tab Code Surface -->
      <section class="editor-stage" id="editorStage">
        <div class="tab-strip" id="editorTabStrip" role="tablist">
          <!-- Dynamic Tabs Rendered Here -->
        </div>

        <div class="editor-viewport" id="editorViewport">
          <div class="line-gutter" id="lineGutter" aria-hidden="true"></div>
          <div class="code-surface" id="codeSurface" contenteditable="false" spellcheck="false" role="textbox" aria-multiline="true">
            <div class="welcome-screen" id="welcomeScreen">
              <h2>Desktop AI Studio</h2>
              <p>Autonomous Pair Programming IDE</p>
              <button class="primary-btn" data-action="open-folder-dialog">Open Project Folder</button>
            </div>
          </div>
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
            <pre class="terminal-view" id="terminalOutput"><code>DeskAI CLI Ready. Connected to Linux GTK bridge.</code></pre>
          </div>
        </section>
      </section>

      <!-- Resizer Handle Right -->
      <div class="resizer-col" id="resizerRight" role="separator" aria-orientation="vertical" tabindex="0"></div>

      <!-- Right Column: Agentic Chat & Morphing UEC Dock -->
      <aside class="sidebar-right" id="sidebarRight" style="width: var(--sidebar-right-w);">
        <div class="chat-header">
          <span class="chat-title">AI PAIR PROGRAMMER</span>
          <span class="model-pill">Qwen 2.5 Coder 7B</span>
        </div>

        <div class="chat-thread" id="chatThread" role="log" aria-live="polite">
          <!-- Chat Bubbles Rendered Here -->
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
    <div id="templateStore" style="display: none;" aria-hidden="true">
      
      <!-- Template: Tree Node -->
      <template id="tplTreeNode">
        <li class="tree-item" role="treeitem" data-path="" data-kind="">
          <span class="tree-chevron">▶</span>
          <span class="tree-icon">📄</span>
          <span class="tree-label">filename.py</span>
          <span class="tree-dirty-dot"></span>
        </li>
      </template>

      <!-- Template: Editor Tab -->
      <template id="tplEditorTab">
        <div class="editor-tab" role="tab" data-tab-id="" data-path="" tabindex="0">
          <span class="tab-icon">📄</span>
          <span class="tab-label">file.py</span>
          <span class="tab-dirty-indicator">●</span>
          <button class="tab-close-btn" data-action="close-tab" aria-label="Close Tab">✕</button>
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
            <button class="uec-btn btn-reject" data-action="uec-reject">Reject</button>
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

---

## 3. HTML5 Template Engine Specification

Browser ke native `<template>` tag ka faida yeh hai ke iska inner markup memory mein parse hota hai magar page load par render ya execute nahi hota.

### Template Instantiation Protocol:
```javascript
export function instantiateTemplate(templateId, dataBindings = {}) {
  const tpl = document.getElementById(templateId);
  if (!tpl) throw new Error(`Template #${templateId} not found.`);

  // Clone template content (True deep clone)
  const clone = tpl.content.cloneNode(true);
  const root = clone.firstElementChild;

  // Apply data-bindings
  for (const [selector, textOrAttrs] of Object.entries(dataBindings)) {
    const el = selector === ":root" ? root : root.querySelector(selector);
    if (!el) continue;

    if (typeof textOrAttrs === "string") {
      el.textContent = textOrAttrs;
    } else if (typeof textOrAttrs === "object") {
      if (textOrAttrs.text) el.textContent = textOrAttrs.text;
      if (textOrAttrs.html) el.innerHTML = textOrAttrs.html;
      if (textOrAttrs.dataset) {
        Object.assign(el.dataset, textOrAttrs.dataset);
      }
      if (textOrAttrs.attrs) {
        for (const [k, v] of Object.entries(textOrAttrs.attrs)) {
          el.setAttribute(k, v);
        }
      }
    }
  }

  return root;
}
```

---

## 4. Standardized `data-action` Protocol

HTML elements par inline `onclick` lagane ke bajaye standardized dataset attributes use kiye gaye hain:

| Element Selector | `data-action` Value | `data-*` Parameters | Description |
|---|---|---|---|
| `.win-btn` | `win-minimize`, `win-maximize`, `win-close` | None | PyWebView native window controls trigger karta hai. |
| `.editor-tab` | `select-tab` | `data-tab-id="uuid"` | Active editor tab switch karta hai. |
| `.tab-close-btn` | `close-tab` | `data-tab-id="uuid"` | Editor tab close karta hai. |
| `.tree-item` | `open-file` | `data-path="/path"` | File buffer load kar ke tab open karta hai. |
| `.uec-btn` | `uec-approve`, `uec-reject` | `data-task-id="uuid"` | AI plan ya code diff accept/reject karta hai. |
| `.palette-trigger-btn` | `open-palette` | None | `<dialog id="commandPaletteDialog">` showModal() call karta hai. |

---

## 5. Accessibility (ARIA) & Keyboard Trapping Standards

1. **Native Dialog Modal Loop:**
   Command Palette ke liye `<dialog>` element ka `showModal()` method use hota hai. Yeh method khud ba khud background DOM ko `inert` kar deta hai aur keyboard focus ko modal ke andar trap karta hai (ESC key par khud close hota hai).
2. **File Tree ARIA Specification:**
   - Container par `role="tree"` aur `tabindex="0"`.
   - Folders par `role="treeitem"` aur `aria-expanded="false" | "true"`.
   - Files par `role="treeitem"` aur `aria-selected="true"`.
3. **Editor Tabs ARIA Specification:**
   - Tab container par `role="tablist"`.
   - Har tab par `role="tab"`, `aria-selected="true" | "false"`.
   - Code surface par `role="tabpanel"`.
