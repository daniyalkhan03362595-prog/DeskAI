/**
 * WelcomeScreenController
 * Manages the reactive state machine and accessible DOM generation for #welcomeScreen.
 */
import { store } from "./state.js";

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
    const openTabs =
      store.state.editor && Array.isArray(store.state.editor.openTabs) ? store.state.editor.openTabs : [];

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
    openFolderBtn.setAttribute("aria-label", "Open Project Folder (Ctrl+O)");

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
    openFileBtn.setAttribute("aria-label", "Open File");

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
    newFileBtn.setAttribute("aria-label", "New File (Ctrl+N)");

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
      { desc: "Focus AI Chat", key: "Ctrl + L" },
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
    newFileBtn.setAttribute("aria-label", "Create New File (Ctrl+N)");

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
    openFileBtn.setAttribute("aria-label", "Open Existing File");

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
    openTermBtn.setAttribute("aria-label", "Open Terminal Here (Ctrl+`)");

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
    switchFolderBtn.setAttribute("aria-label", "Switch Project Folder");

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
      { desc: "Ask AI Assistant", key: "Ctrl + L" },
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
      return list.filter((item) => item && typeof item.path === "string" && typeof item.name === "string");
    } catch {
      return [];
    }
  }

  saveRecentProject(path, name) {
    if (!path || !name) return;
    try {
      let list = this.loadRecentProjects();
      list = list.filter((p) => p.path !== path);
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
      list = list.filter((p) => p.path !== path);
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
