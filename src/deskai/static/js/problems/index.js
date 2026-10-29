/**
 * DeskAI Problems Manager (window.DeskAIProblems).
 * Orchestrates diagnostics checking on save/manual scan, store updates, and view rendering.
 */

import { DiagnosticsStore } from "./store.js";
import { renderGroups, initViewKeyboardAndClicks } from "./view.js";
import { NativeBridge } from "../bridge.js";
import { store } from "../state.js";
import { createSvgIcon } from "../icons.js";

export class ProblemsManager {
  constructor() {
    this.store = new DiagnosticsStore();
    this.collapsed = new Set();
    this.activeFilters = new Set(["error", "warning", "info"]);
    this.filterQuery = "";
    this.generation = 0;
    this._latest = new Map();
    this._reqSeq = 0;
    this._debounceTimers = new Map();
    this._announceTimer = null;
    this._renderedVersion = -1;
    this.focusedId = null;

    this.container = document.getElementById("problemsView");
    this.noticeEl = document.getElementById("problemsNotice");
    this.tabBadge = document.getElementById("problemsTabBadge");
    this.tabBtn = document.getElementById("tab-problems");
    this.filterInput = document.getElementById("problemsFilterInput");

    this._initToolbarIcons();
    this._initEvents();

    this.store.subscribe(() => {
      this.render();
      this._syncCounts();
    });

    if (store && typeof store.subscribe === "function") {
      store.subscribe("workspace.rootPath", () => {
        this.reset();
      });
    }

    if (this.container) {
      initViewKeyboardAndClicks(this.container, this, (file, line, col) => {
        this.navigateTo(file, line, col);
      });
    }

    this._syncCounts();
  }

  _initToolbarIcons() {
    const collapseBtn = document.querySelector('[data-action="problems-collapse"]');
    if (collapseBtn && collapseBtn.children.length === 0) {
      collapseBtn.appendChild(createSvgIcon("collapse-all", 14));
    }
    const runBtn = document.getElementById("problemsRunBtn");
    if (runBtn && runBtn.children.length === 0) {
      runBtn.appendChild(createSvgIcon("refresh", 14));
    }
  }

  _initEvents() {
    if (this.filterInput) {
      this.filterInput.addEventListener("input", (e) => {
        this.setFilterQuery(e.target.value.trim());
      });
    }
  }

  idFor(file) {
    return String(file).replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  toggleCollapse(file) {
    if (this.collapsed.has(file)) {
      this.collapsed.delete(file);
    } else {
      this.collapsed.add(file);
    }
    this.render();
  }

  toggleCollapseAll() {
    const grouped = this.store.grouped({ severities: this.activeFilters, query: this.filterQuery });
    const allFiles = Array.from(grouped.keys());
    const allCollapsed = allFiles.every(f => this.collapsed.has(f));

    if (allCollapsed) {
      this.collapsed.clear();
    } else {
      for (const f of allFiles) {
        this.collapsed.add(f);
      }
    }
    this.render();
  }

  toggleFilter(severity) {
    const btn = document.querySelector(`.problems-filter[data-severity="${severity}"]`);
    if (this.activeFilters.has(severity)) {
      this.activeFilters.delete(severity);
      if (btn) btn.setAttribute("aria-pressed", "false");
    } else {
      this.activeFilters.add(severity);
      if (btn) btn.setAttribute("aria-pressed", "true");
    }
    this.render();
  }

  setFilterQuery(query) {
    this.filterQuery = query || "";
    this.render();
  }

  onShow() {
    if (this._renderedVersion !== this.store.signature()) {
      this.render();
    }
  }

  render() {
    if (!this.container) return;
    this._renderedVersion = this.store.signature();
    const grouped = this.store.grouped({
      severities: this.activeFilters,
      query: this.filterQuery
    });
    renderGroups(this.container, grouped, this);
  }

  onFileSaved(filePath) {
    if (!filePath) return;
    const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
    if (root) {
      const cleanRoot = root.replace(/\\/g, "/").toLowerCase();
      const cleanPath = filePath.replace(/\\/g, "/").toLowerCase();
      if (!cleanPath.startsWith(cleanRoot)) {
        return;
      }
    }

    const key = DiagnosticsStore.key(filePath);
    if (this._debounceTimers.has(key)) {
      clearTimeout(this._debounceTimers.get(key));
    }

    const timer = setTimeout(() => {
      this._debounceTimers.delete(key);
      this._check(filePath);
    }, 300);

    this._debounceTimers.set(key, timer);
  }

  onPathRemoved(filePath) {
    if (!filePath) return;
    this.store.clearFile(filePath);
  }

  async _check(filePath) {
    const gen = this.generation;
    const reqId = ++this._reqSeq;
    const key = DiagnosticsStore.key(filePath);
    this._latest.set(key, reqId);

    if (store && store.state && store.state.diagnostics) {
      store.state.diagnostics.status = "checking";
    }

    const res = await NativeBridge.runDiagnostics(filePath, reqId);

    if (gen !== this.generation) return;
    if (this._latest.get(key) !== reqId) return;

    if (res.status !== "ok") {
      this._setNotice(res.message || "Diagnostics failed");
      return;
    }

    this._clearNotice();

    // Collect all sources to replace
    const sourcesToUpdate = new Set();
    if (res.diagnostics) {
      for (const d of res.diagnostics) {
        if (d.source) sourcesToUpdate.add(d.source);
      }
    }
    // Also include default built-in checkers for file extension
    const ext = filePath.includes(".") ? filePath.substring(filePath.lastIndexOf(".")).toLowerCase() : "";
    if (ext === ".py" || ext === ".pyw") {
      sourcesToUpdate.add("python");
    } else if (ext === ".json") {
      sourcesToUpdate.add("json");
    }

    for (const source of sourcesToUpdate) {
      const filtered = (res.diagnostics || []).filter(d => d.source === source);
      this.store.replace(source, res.file, filtered);
    }

    if (store && store.state && store.state.diagnostics) {
      store.state.diagnostics.status = "done";
      store.state.diagnostics.checkedAt = Date.now();
    }

    this._syncCounts();
    this._announce();
  }

  async runWorkspace({ silent = false } = {}) {
    const runBtn = document.getElementById("problemsRunBtn");
    if (runBtn && !silent) {
      runBtn.classList.add("is-refreshing");
      setTimeout(() => runBtn.classList.remove("is-refreshing"), 400);
    }

    const panel = document.getElementById("problemsPanel");
    if (panel) panel.setAttribute("data-busy", "true");

    try {
      const reqId = ++this._reqSeq;
      const res = await NativeBridge.runWorkspaceDiagnostics(reqId);
      if (res && res.status === "ok" && res.files) {
        this.store.replaceAllWorkspace(res.files);
      }
    } catch (e) {
      console.error("[ProblemsManager] runWorkspace error:", e);
    } finally {
      if (panel) panel.removeAttribute("data-busy");
      this._syncCounts();
      this._announce();
    }
  }

  reset() {
    this.generation++;
    for (const timer of this._debounceTimers.values()) {
      clearTimeout(timer);
    }
    this._debounceTimers.clear();
    this._latest.clear();
    this.collapsed.clear();
    this.store.clearAll();
    this._clearNotice();

    if (store && store.state && store.state.diagnostics) {
      store.state.diagnostics.errors = 0;
      store.state.diagnostics.warnings = 0;
      store.state.diagnostics.infos = 0;
      store.state.diagnostics.status = "idle";
      store.state.diagnostics.checkedAt = null;
    }

    this._syncCounts();
  }

  _syncCounts() {
    const counts = this.store.counts();
    const errCountEl = document.getElementById("problemsErrCount");
    const warnCountEl = document.getElementById("problemsWarnCount");
    const infoCountEl = document.getElementById("problemsInfoCount");

    if (errCountEl) errCountEl.textContent = String(counts.errors);
    if (warnCountEl) warnCountEl.textContent = String(counts.warnings);
    if (infoCountEl) infoCountEl.textContent = String(counts.infos);

    if (store && store.state && store.state.diagnostics) {
      store.state.diagnostics.errors = counts.errors;
      store.state.diagnostics.warnings = counts.warnings;
      store.state.diagnostics.infos = counts.infos;
    }

    const total = counts.errors + counts.warnings;
    if (this.tabBadge) {
      if (total > 0) {
        this.tabBadge.hidden = false;
        this.tabBadge.textContent = String(total);
      } else {
        this.tabBadge.hidden = true;
      }
    }

    if (this.tabBtn) {
      if (total > 0) {
        const errStr = `${counts.errors} error${counts.errors === 1 ? "" : "s"}`;
        const warnStr = `${counts.warnings} warning${counts.warnings === 1 ? "" : "s"}`;
        this.tabBtn.setAttribute("aria-label", `Problems, ${errStr}, ${warnStr}`);
      } else {
        this.tabBtn.setAttribute("aria-label", "Problems, no problems");
      }
    }
  }

  _announce() {
    if (this._announceTimer) {
      clearTimeout(this._announceTimer);
    }
    this._announceTimer = setTimeout(() => {
      const announcer = document.getElementById("screenReaderAnnouncer");
      if (!announcer) return;
      const counts = this.store.counts();
      const total = counts.errors + counts.warnings;
      if (total > 0) {
        announcer.textContent = `Checks complete: ${counts.errors} errors, ${counts.warnings} warnings`;
      } else {
        announcer.textContent = "No problems detected";
      }
    }, 500);
  }

  _setNotice(msg) {
    if (this.noticeEl) {
      this.noticeEl.textContent = msg;
      this.noticeEl.hidden = false;
    }
  }

  _clearNotice() {
    if (this.noticeEl) {
      this.noticeEl.textContent = "";
      this.noticeEl.hidden = true;
    }
  }

  async navigateTo(relFile, line, col) {
    if (!relFile) return;
    const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
    const cleanRoot = root ? root.replace(/\/+$/, "") : "";
    const cleanRel = relFile.replace(/^\/+/, "");
    const fullPath = cleanRoot ? `${cleanRoot}/${cleanRel}` : cleanRel;

    if (window.EditorManager && typeof window.EditorManager.openAt === "function") {
      await window.EditorManager.openAt(fullPath, line, col);
    } else if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
      await window.EditorManager.openFile(fullPath);
    }
  }
}

export function initProblems() {
  return new ProblemsManager();
}
