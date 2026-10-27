# Low-Level Design (LLD): Welcome Screen Overlay

**Document ID:** `ORX-LLD-WELCOME-SCREEN-OVERLAY-V1`  
**Version:** `1.0` (Reactive State-Driven Studio Hub Architecture)  
**Parent Document:** `ORX-HLD-WELCOME-SCREEN-OVERLAY-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/welcome.js`
* `src/deskai/static/js/editor.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/static/js/state.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_welcome_screen_overlay.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Welcome Screen Overlay** (`#welcomeScreen`) is the primary interactive empty-state canvas occupying `#editorViewport` in DeskAI. It is displayed whenever there are no active editor tab buffers open (`store.state.editor.openTabs.length === 0`).

This Low-Level Design specification defines:
1. The exact DOM structure and accessible markup hierarchy.
2. The CSS token mappings adhering to the Obsidian Matte + Warm Amber design system.
3. The JavaScript class architecture for `WelcomeScreenController` in `src/deskai/static/js/welcome.js`.
4. The fixes in `src/deskai/static/js/bridge.js` ensuring bridge readiness before native OS dialog invocation.
5. The centralized event delegation handling in `src/deskai/static/js/events.js`.
6. Concrete Playwright end-to-end test cases and unit assertions (`TC-WSO-01` through `TC-WSO-08`).

---

## 2. DOM Hierarchy & Component Layout

The overlay sits inside `#editorViewport` alongside `#codeEditorHost`.

```html
<div class="editor-viewport" id="editorViewport" role="tabpanel" aria-label="Active File Editor">
  <!-- Welcome Screen Overlay Root -->
  <div 
    class="welcome-screen" 
    id="welcomeScreen" 
    role="region" 
    aria-label="Welcome and Quick Actions" 
    tabindex="-1">
    
    <div class="welcome-container" id="welcomeContainer">
      <!-- 1. Brand Header -->
      <header class="welcome-header">
        <div class="welcome-badge">
          <span class="welcome-badge-icon" aria-hidden="true">⚡</span>
          <span class="welcome-badge-text">DeskAI Studio</span>
        </div>
        <h1 class="welcome-title" id="welcomeTitle">Welcome to DeskAI</h1>
        <p class="welcome-subtitle" id="welcomeSubtitle">Local-first autonomous AI developer studio</p>
      </header>

      <!-- 2. Main Content Grid (Dynamically Populated) -->
      <main class="welcome-grid" id="welcomeGrid">
        <!-- Rendered dynamically by WelcomeScreenController via createElement/textContent -->
      </main>

      <!-- 3. Accessible Live Region for Screen Reader Announcements -->
      <div class="sr-only" id="welcomeSrLive" role="status" aria-live="polite"></div>
    </div>
  </div>

  <!-- CodeMirror 6 Surface Host (Visible when openTabs.length > 0) -->
  <div class="codemirror-host" id="codeEditorHost" role="region" aria-label="Code Surface"></div>
</div>
```

---

## 3. Visual Styling & CSS Token Bindings (`src/deskai/static/css/components.css`)

All colors and spacing use CSS variables defined in `src/deskai/static/css/tokens.css`.

```css
/* ==========================================================================
   Welcome Screen Overlay Component
   ========================================================================== */

.welcome-screen {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
  background-color: var(--bg-surface);
  overflow-y: auto;
  z-index: var(--z-content);
}

.welcome-screen[hidden] {
  display: none !important;
}

.welcome-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 680px;
  width: 100%;
  gap: var(--space-6);
}

/* Header & Brand Identity */
.welcome-header {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.welcome-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 4px 10px;
  background-color: var(--color-amber-surface);
  border: 1px solid var(--border-focus);
  border-radius: var(--radius-pill);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-amber);
}

.welcome-title {
  color: var(--text-primary);
  font-size: var(--text-xl);
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.02em;
}

.welcome-subtitle {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin: 0;
}

/* Main Two-Column Grid */
.welcome-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  width: 100%;
}

@media (max-width: 640px) {
  .welcome-grid {
    grid-template-columns: 1fr;
  }
}

/* Panel Card Surfaces */
.welcome-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.welcome-card-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* Action Button Stack */
.welcome-action-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.welcome-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
  text-align: left;
}

.welcome-btn.primary {
  background-color: var(--color-primary);
  color: var(--text-btn-primary);
  border-color: var(--color-primary-hover);
  font-weight: 600;
}

.welcome-btn.primary:hover {
  background-color: var(--color-primary-hover);
}

.welcome-btn.secondary {
  background-color: var(--bg-surface-elevated);
  color: var(--text-primary);
  border-color: var(--border-regular);
}

.welcome-btn.secondary:hover {
  background-color: var(--bg-hover);
  border-color: var(--color-primary);
}

.welcome-btn-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.welcome-btn-shortcut {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  background-color: var(--bg-surface);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}

/* Recent Projects List */
.welcome-recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.welcome-recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background-color: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.welcome-recent-item:hover {
  background-color: var(--bg-hover);
  border-color: var(--color-primary);
}

.welcome-recent-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.welcome-recent-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.welcome-recent-path {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
}

.welcome-recent-remove {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.welcome-recent-remove:hover {
  color: var(--color-danger);
  background-color: var(--color-danger-subtle);
}

/* Keyboard Shortcut List */
.welcome-shortcut-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.welcome-shortcut-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.welcome-shortcut-key {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  background-color: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  color: var(--text-primary);
}

/* Workspace Active Hub Banner */
.welcome-workspace-banner {
  background-color: var(--color-amber-surface);
  border: 1px solid var(--border-focus);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
}

.welcome-workspace-icon {
  font-size: var(--text-lg);
}

.welcome-workspace-details {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.welcome-workspace-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-amber);
}

.welcome-workspace-path {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

---

## 4. Component Controller Specification (`src/deskai/static/js/welcome.js`)

```javascript
/**
 * WelcomeScreenController
 * Manages the reactive state machine and accessible DOM generation for #welcomeScreen.
 */
import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";

export class WelcomeScreenController {
  constructor(rootEl = document.getElementById("welcomeScreen")) {
    this.root = rootEl;
    this.container = rootEl ? rootEl.querySelector("#welcomeContainer") : null;
    this.grid = rootEl ? rootEl.querySelector("#welcomeGrid") : null;
    this.title = rootEl ? rootEl.querySelector("#welcomeTitle") : null;
    this.subtitle = rootEl ? rootEl.querySelector("#welcomeSubtitle") : null;
    this.srLive = rootEl ? rootEl.querySelector("#welcomeSrLive") : null;
    
    this.RECENT_KEY = "deskai_recent_projects";
    this.MAX_RECENT = 5;

    this._bindStore();
  }

  _bindStore() {
    if (store && typeof store.subscribe === "function") {
      store.subscribe("workspace.rootPath", () => this.sync());
      store.subscribe("editor.openTabs", () => this.sync());
    }
  }

  /**
   * Evaluates state machine and synchronizes visibility and view model.
   */
  sync() {
    if (!this.root || !this.grid) return;

    const rootPath = store.state.workspace ? store.state.workspace.rootPath : null;
    const openTabs = store.state.editor && Array.isArray(store.state.editor.openTabs) 
      ? store.state.editor.openTabs 
      : [];

    // State 3: HIDDEN
    if (openTabs.length > 0) {
      this.root.hidden = true;
      this.root.setAttribute("aria-hidden", "true");
      this.root.style.display = "none";
      return;
    }

    // Overlay is active
    this.root.hidden = false;
    this.root.removeAttribute("aria-hidden");
    this.root.style.display = "flex";

    if (rootPath) {
      this._renderWorkspaceState(rootPath);
    } else {
      this._renderEmptyState();
    }
  }

  /**
   * State 1: EMPTY_NO_WORKSPACE
   */
  _renderEmptyState() {
    if (this.title) this.title.textContent = "Welcome to DeskAI";
    if (this.subtitle) this.subtitle.textContent = "Open a project directory or file to begin development.";
    this.grid.replaceChildren();

    // Column 1: Start Actions & Recent Projects
    const leftCol = document.createElement("div");
    leftCol.className = "welcome-card";

    const startTitle = document.createElement("h2");
    startTitle.className = "welcome-card-title";
    startTitle.textContent = "Get Started";
    leftCol.appendChild(startTitle);

    const actionStack = document.createElement("div");
    actionStack.className = "welcome-action-stack";

    // Primary CTA: Open Folder
    const openFolderBtn = document.createElement("button");
    openFolderBtn.type = "button";
    openFolderBtn.id = "welcomePrimaryBtn";
    openFolderBtn.className = "welcome-btn primary";
    openFolderBtn.setAttribute("data-action", "open-folder-dialog");
    
    const openFolderLabel = document.createElement("span");
    openFolderLabel.className = "welcome-btn-label";
    openFolderLabel.textContent = "📁 Open Project Folder";
    
    const openFolderKey = document.createElement("span");
    openFolderKey.className = "welcome-btn-shortcut";
    openFolderKey.textContent = "Ctrl+O";
    
    openFolderBtn.appendChild(openFolderLabel);
    openFolderBtn.appendChild(openFolderKey);
    actionStack.appendChild(openFolderBtn);

    // Secondary CTA: Open File
    const openFileBtn = document.createElement("button");
    openFileBtn.type = "button";
    openFileBtn.className = "welcome-btn secondary";
    openFileBtn.setAttribute("data-action", "open-file-dialog");
    
    const openFileLabel = document.createElement("span");
    openFileLabel.className = "welcome-btn-label";
    openFileLabel.textContent = "📄 Open File";
    
    openFileBtn.appendChild(openFileLabel);
    actionStack.appendChild(openFileBtn);

    // New Untitled Buffer
    const newFileBtn = document.createElement("button");
    newFileBtn.type = "button";
    newFileBtn.className = "welcome-btn secondary";
    newFileBtn.setAttribute("data-action", "new-file");
    
    const newFileLabel = document.createElement("span");
    newFileLabel.className = "welcome-btn-label";
    newFileLabel.textContent = "✨ New File";
    
    const newFileKey = document.createElement("span");
    newFileKey.className = "welcome-btn-shortcut";
    newFileKey.textContent = "Ctrl+N";
    
    newFileBtn.appendChild(newFileLabel);
    newFileBtn.appendChild(newFileKey);
    actionStack.appendChild(newFileBtn);

    leftCol.appendChild(actionStack);

    // Recent Projects Subsection
    const recentProjects = this.loadRecentProjects();
    if (recentProjects.length > 0) {
      const recentHeader = document.createElement("h2");
      recentHeader.className = "welcome-card-title";
      recentHeader.style.marginTop = "var(--space-2)";
      recentHeader.textContent = "Recent Projects";
      leftCol.appendChild(recentHeader);

      const recentList = document.createElement("ul");
      recentList.className = "welcome-recent-list";

      for (const item of recentProjects) {
        const li = document.createElement("li");
        li.className = "welcome-recent-item";
        li.setAttribute("data-action", "open-recent-project");
        li.setAttribute("data-param", item.path);
        li.setAttribute("tabindex", "0");
        li.setAttribute("role", "button");
        li.setAttribute("aria-label", `Open recent project ${item.name}`);

        const info = document.createElement("div");
        info.className = "welcome-recent-info";
        
        const nameSpan = document.createElement("span");
        nameSpan.className = "welcome-recent-name";
        nameSpan.textContent = item.name;
        
        const pathSpan = document.createElement("span");
        pathSpan.className = "welcome-recent-path";
        pathSpan.textContent = item.path;
        
        info.appendChild(nameSpan);
        info.appendChild(pathSpan);
        li.appendChild(info);

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "welcome-recent-remove";
        removeBtn.setAttribute("data-action", "remove-recent-project");
        removeBtn.setAttribute("data-param", item.path);
        removeBtn.setAttribute("aria-label", `Remove ${item.name} from recent list`);
        removeBtn.textContent = "✕";
        li.appendChild(removeBtn);

        recentList.appendChild(li);
      }
      leftCol.appendChild(recentList);
    }

    // Column 2: Keyboard Shortcuts & Help
    const rightCol = document.createElement("div");
    rightCol.className = "welcome-card";

    const shortcutTitle = document.createElement("h2");
    shortcutTitle.className = "welcome-card-title";
    shortcutTitle.textContent = "Keyboard Shortcuts";
    rightCol.appendChild(shortcutTitle);

    const shortcutList = document.createElement("div");
    shortcutList.className = "welcome-shortcut-list";

    const shortcuts = [
      { desc: "Open Folder", key: "Ctrl + O" },
      { desc: "New Untitled File", key: "Ctrl + N" },
      { desc: "Save Active File", key: "Ctrl + S" },
      { desc: "Toggle Bottom Drawer", key: "Ctrl + `" },
      { desc: "Focus AI Chat", key: "Ctrl + L" }
    ];

    for (const sc of shortcuts) {
      const row = document.createElement("div");
      row.className = "welcome-shortcut-row";
      
      const desc = document.createElement("span");
      desc.textContent = sc.desc;
      
      const kbd = document.createElement("kbd");
      kbd.className = "welcome-shortcut-key";
      kbd.textContent = sc.key;
      
      row.appendChild(desc);
      row.appendChild(kbd);
      shortcutList.appendChild(row);
    }
    rightCol.appendChild(shortcutList);

    this.grid.appendChild(leftCol);
    this.grid.appendChild(rightCol);

    this._announceState("Welcome screen active. No workspace open.");
  }

  /**
   * State 2: WORKSPACE_NO_TABS
   */
  _renderWorkspaceState(rootPath) {
    const folderName = rootPath.split("/").pop().split("\\").pop() || rootPath;
    if (this.title) this.title.textContent = `Workspace: ${folderName}`;
    if (this.subtitle) this.subtitle.textContent = "Workspace is active. Select or create a file to start editing.";
    this.grid.replaceChildren();

    // Full-width Active Workspace Banner
    const banner = document.createElement("div");
    banner.className = "welcome-workspace-banner";
    banner.style.gridColumn = "1 / -1";

    const icon = document.createElement("span");
    icon.className = "welcome-workspace-icon";
    icon.textContent = "📁";
    
    const details = document.createElement("div");
    details.className = "welcome-workspace-details";
    
    const wsTitle = document.createElement("span");
    wsTitle.className = "welcome-workspace-title";
    wsTitle.textContent = folderName;
    
    const wsPath = document.createElement("span");
    wsPath.className = "welcome-workspace-path";
    wsPath.textContent = rootPath;
    
    details.appendChild(wsTitle);
    details.appendChild(wsPath);
    banner.appendChild(icon);
    banner.appendChild(details);
    this.grid.appendChild(banner);

    // Left Column: Quick File Actions
    const leftCol = document.createElement("div");
    leftCol.className = "welcome-card";

    const actionsTitle = document.createElement("h2");
    actionsTitle.className = "welcome-card-title";
    actionsTitle.textContent = "Workspace Actions";
    leftCol.appendChild(actionsTitle);

    const actionStack = document.createElement("div");
    actionStack.className = "welcome-action-stack";

    // Primary CTA: New File
    const newFileBtn = document.createElement("button");
    newFileBtn.type = "button";
    newFileBtn.id = "welcomePrimaryBtn";
    newFileBtn.className = "welcome-btn primary";
    newFileBtn.setAttribute("data-action", "new-file");
    
    const newFileLabel = document.createElement("span");
    newFileLabel.className = "welcome-btn-label";
    newFileLabel.textContent = "✨ Create New File";
    
    const newFileKey = document.createElement("span");
    newFileKey.className = "welcome-btn-shortcut";
    newFileKey.textContent = "Ctrl+N";
    
    newFileBtn.appendChild(newFileLabel);
    newFileBtn.appendChild(newFileKey);
    actionStack.appendChild(newFileBtn);

    // Open File in Workspace
    const openFileBtn = document.createElement("button");
    openFileBtn.type = "button";
    openFileBtn.className = "welcome-btn secondary";
    openFileBtn.setAttribute("data-action", "open-file-dialog");
    
    const openFileLabel = document.createElement("span");
    openFileLabel.className = "welcome-btn-label";
    openFileLabel.textContent = "📄 Open Existing File";
    
    openFileBtn.appendChild(openFileLabel);
    actionStack.appendChild(openFileBtn);

    // Open Terminal Here
    const openTermBtn = document.createElement("button");
    openTermBtn.type = "button";
    openTermBtn.className = "welcome-btn secondary";
    openTermBtn.setAttribute("data-action", "drawer-tab");
    openTermBtn.setAttribute("data-target", "terminal");
    
    const openTermLabel = document.createElement("span");
    openTermLabel.className = "welcome-btn-label";
    openTermLabel.textContent = "💻 Open Terminal Here";
    
    const openTermKey = document.createElement("span");
    openTermKey.className = "welcome-btn-shortcut";
    openTermKey.textContent = "Ctrl+`";
    
    openTermBtn.appendChild(openTermLabel);
    openTermBtn.appendChild(openTermKey);
    actionStack.appendChild(openTermBtn);

    // Change Workspace Folder
    const switchFolderBtn = document.createElement("button");
    switchFolderBtn.type = "button";
    switchFolderBtn.className = "welcome-btn secondary";
    switchFolderBtn.setAttribute("data-action", "open-folder-dialog");
    
    const switchLabel = document.createElement("span");
    switchLabel.className = "welcome-btn-label";
    switchLabel.textContent = "🔄 Switch Project Folder";
    
    switchFolderBtn.appendChild(switchLabel);
    actionStack.appendChild(switchFolderBtn);

    leftCol.appendChild(actionStack);

    // Right Column: Short Tips
    const rightCol = document.createElement("div");
    rightCol.className = "welcome-card";

    const tipsTitle = document.createElement("h2");
    tipsTitle.className = "welcome-card-title";
    tipsTitle.textContent = "Quick Tips";
    rightCol.appendChild(tipsTitle);

    const shortcutList = document.createElement("div");
    shortcutList.className = "welcome-shortcut-list";

    const tips = [
      { desc: "Create File", key: "Ctrl + N" },
      { desc: "Save Changes", key: "Ctrl + S" },
      { desc: "Toggle Terminal", key: "Ctrl + `" },
      { desc: "Ask AI Assistant", key: "Ctrl + L" }
    ];

    for (const t of tips) {
      const row = document.createElement("div");
      row.className = "welcome-shortcut-row";
      
      const desc = document.createElement("span");
      desc.textContent = t.desc;
      
      const kbd = document.createElement("kbd");
      kbd.className = "welcome-shortcut-key";
      kbd.textContent = t.key;
      
      row.appendChild(desc);
      row.appendChild(kbd);
      shortcutList.appendChild(row);
    }
    rightCol.appendChild(shortcutList);

    this.grid.appendChild(leftCol);
    this.grid.appendChild(rightCol);

    this._announceState(`Workspace ${folderName} active. No open files.`);
  }

  loadRecentProjects() {
    try {
      const raw = localStorage.getItem(this.RECENT_KEY);
      if (!raw) return [];
      const list = JSON.parse(raw);
      if (!Array.isArray(list)) return [];
      return list.filter(item => item && typeof item.path === "string" && typeof item.name === "string");
    } catch {
      return [];
    }
  }

  saveRecentProject(path, name) {
    if (!path || !name) return;
    try {
      let list = this.loadRecentProjects();
      list = list.filter(p => p.path !== path);
      list.unshift({ path, name, lastOpened: Date.now() });
      if (list.length > this.MAX_RECENT) {
        list = list.slice(0, this.MAX_RECENT);
      }
      localStorage.setItem(this.RECENT_KEY, JSON.stringify(list));
    } catch (e) {
      console.warn("Failed to persist recent project:", e);
    }
  }

  removeRecentProject(path) {
    try {
      let list = this.loadRecentProjects();
      list = list.filter(p => p.path !== path);
      localStorage.setItem(this.RECENT_KEY, JSON.stringify(list));
      this.sync();
    } catch (e) {
      console.warn("Failed to remove recent project:", e);
    }
  }

  focusPrimary() {
    const primaryBtn = this.root ? this.root.querySelector("#welcomePrimaryBtn") : null;
    if (primaryBtn) {
      primaryBtn.focus();
    }
  }

  _announceState(message) {
    if (this.srLive) {
      this.srLive.textContent = message;
    }
  }
}
```

---

## 5. NativeBridge Enhancements (`src/deskai/static/js/bridge.js`)

To fix the race condition where `selectFolder()` failed when invoked prior to pywebview initialization, `whenReady()` is awaited:

```javascript
// In src/deskai/static/js/bridge.js
async selectFolder() {
  await this.whenReady();
  if (window.pywebview && window.pywebview.api) {
    return await window.pywebview.api.select_folder();
  }
  console.warn("[Bridge] pywebview.api not ready.");
  return { status: "cancelled", path: null };
},

async selectFile() {
  await this.whenReady();
  if (window.pywebview && window.pywebview.api) {
    return await window.pywebview.api.select_file();
  }
  return { status: "cancelled", path: null };
},
```

---

## 6. Event Handling & Centralized Delegation (`src/deskai/static/js/events.js`)

Add routing cases for the Welcome Screen actions:

```javascript
// In src/deskai/static/js/events.js inside document.addEventListener("click", async (e) => { ... })
case "open-folder-dialog": {
  const dir = await NativeBridge.selectFolder();
  if (dir && dir.path) {
    store.state.workspace.rootPath = dir.path;
    const pill = document.getElementById("headerWorkspacePill");
    if (pill) pill.textContent = `DeskAI / ${dir.name}`;
    if (window.DeskAIWelcome) {
      window.DeskAIWelcome.saveRecentProject(dir.path, dir.name);
      window.DeskAIWelcome.sync();
    }
  }
  break;
}

case "open-file-dialog": {
  const fileRes = await NativeBridge.selectFile();
  if (fileRes && fileRes.path) {
    const contentRes = await NativeBridge.readFile(fileRes.path);
    const content = contentRes && contentRes.status === "ok" ? contentRes.content : "";
    window.EditorManager.createBuffer(fileRes.name, content, fileRes.path);
  }
  break;
}

case "open-recent-project": {
  if (param) {
    store.state.workspace.rootPath = param;
    const name = param.split("/").pop().split("\\").pop() || param;
    const pill = document.getElementById("headerWorkspacePill");
    if (pill) pill.textContent = `DeskAI / ${name}`;
    if (window.DeskAIWelcome) {
      window.DeskAIWelcome.saveRecentProject(param, name);
      window.DeskAIWelcome.sync();
    }
  }
  break;
}

case "remove-recent-project": {
  e.stopPropagation();
  if (param && window.DeskAIWelcome) {
    window.DeskAIWelcome.removeRecentProject(param);
  }
  break;
}
```

---

## 7. Concrete Test Specifications (`tests/test_welcome_screen_overlay.py`)

### `TC-WSO-01`: Accessible Markup & Role Verification
* **Setup:** Launch headless Chromium with `index.html`.
* **Execution:** Inspect `#welcomeScreen`.
* **Assertions:**
  1. `#welcomeScreen` element exists.
  2. Attribute `role="region"` is present.
  3. Attribute `aria-label="Welcome and Quick Actions"` is present.

### `TC-WSO-02`: Initial State `EMPTY_NO_WORKSPACE`
* **Setup:** Load app with default store (`rootPath = null`, `openTabs = []`).
* **Assertions:**
  1. `#welcomeScreen` has `display: flex` and is NOT hidden.
  2. `#welcomeTitle` contains "Welcome to DeskAI".
  3. Button `[data-action="open-folder-dialog"]` is present and visible.
  4. Shortcut cheatsheet displays `Ctrl + O` and `Ctrl + N`.

### `TC-WSO-03`: Transition to `WORKSPACE_NO_TABS`
* **Setup:** Trigger state mutation: `store.state.workspace.rootPath = "/test/my-project"`.
* **Assertions:**
  1. `#welcomeScreen` remains visible (`display: flex`).
  2. Banner displays folder name `"my-project"` and path `"/test/my-project"`.
  3. Primary CTA updates to `[New File]`.
  4. Quick action buttons include `[Open Existing File]` and `[Open Terminal Here]`.

### `TC-WSO-04`: Transition to `HIDDEN` on Buffer Creation
* **Setup:** Call `window.EditorManager.createBuffer("main.py", "print(1)")`.
* **Assertions:**
  1. `#welcomeScreen` has `style.display === "none"` or `hidden` attribute.
  2. `aria-hidden="true"` is set on `#welcomeScreen`.
  3. `#codeEditorHost` is visible.

### `TC-WSO-05`: Transition Back to `WORKSPACE_NO_TABS` on Tab Closure
* **Setup:** From state with 1 buffer, call `window.EditorManager.closeTab(tabId)`.
* **Assertions:**
  1. `openTabs` count drops to 0.
  2. `#welcomeScreen` re-appears with `style.display === "flex"`.
  3. Title displays `"Workspace: my-project"`.

### `TC-WSO-06`: Native Bridge Readiness Handshake
* **Setup:** Click `[data-action="open-folder-dialog"]` before mocking `window.pywebview.api`.
* **Assertions:**
  1. `NativeBridge.selectFolder()` does not immediately throw or cancel; it waits on `whenReady()`.
  2. Once `pywebviewready` event is dispatched or api is attached, dialog succeeds.

### `TC-WSO-07`: Keyboard Roving & Visual Focus
* **Setup:** Focus `#welcomeScreen` and simulate `Tab` key traversal.
* **Assertions:**
  1. Initial focus lands on `#welcomePrimaryBtn`.
  2. Focus outline matches `var(--color-primary)`.
  3. Pressing `Enter` triggers button click handler.

### `TC-WSO-08`: Strict XSS Mitigation on Malicious Workspace Paths
* **Setup:** Set `rootPath = "<script>alert('xss')</script><img src=x onerror=alert(1)>"`.
* **Assertions:**
  1. No script executes.
  2. No `<img>` tags are injected into DOM.
  3. InnerHTML of path containers contains escaped text entities (`&lt;script&gt;`).

---

## 8. Implementation Checklist

- [ ] Create `src/deskai/static/js/welcome.js` implementing `WelcomeScreenController`.
- [ ] Export and instantiate singleton `window.DeskAIWelcome` in `src/deskai/static/js/app.js`.
- [ ] Update `src/deskai/static/js/bridge.js` to await `whenReady()` in `selectFolder()` and `selectFile()`.
- [ ] Update `src/deskai/static/js/events.js` to handle `open-folder-dialog`, `open-file-dialog`, `open-recent-project`, `remove-recent-project`.
- [ ] Update `src/deskai/static/js/editor.js` to delegate overlay visibility toggles to `window.DeskAIWelcome.sync()`.
- [ ] Update `src/deskai/static/index.html` with accessible landmarks and container hooks.
- [ ] Update `src/deskai/static/css/components.css` with token-driven responsive card styles.
- [ ] Create Playwright & unit test suite in `tests/test_welcome_screen_overlay.py`.
