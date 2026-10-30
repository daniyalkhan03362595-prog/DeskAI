/**
 * OutputManager: Coordinates live system and channel logs for DeskAI Studio.
 * Wires the OutputClient to LogView, manages filters, toolbar toggles, accessibility announcements,
 * unread badges, and local logging.
 */

import { announce } from "../terminal.js";
import { createSvgIcon } from "../icons.js";
import { store } from "../state.js";
import { NativeBridge } from "../bridge.js";
import { OutputClient } from "./client.js";

export class OutputManager {
  constructor(panelEl, view) {
    this.panelEl = panelEl;
    this.view = view;
    this.tabEl = document.getElementById("tab-output");
    this.statusEl = document.getElementById("outputStatus");
    this.jumpBtn = document.getElementById("outputJump");
    this.channelSelect = document.getElementById("outputChannelSelect");
    this.levelSelect = document.getElementById("outputLevelSelect");
    this.filterInput = document.getElementById("outputFilterInput");

    this.timeBtn = panelEl.querySelector('[data-action="output-time"]');
    this.wrapBtn = panelEl.querySelector('[data-action="output-wrap"]');
    this.copyBtn = panelEl.querySelector('[data-action="output-copy"]');
    this.saveBtn = panelEl.querySelector('[data-action="output-save"]');
    this.clearBtn = panelEl.querySelector('[data-action="output-clear"]');

    this.isActive = false;
    this.unreadErrors = 0;
    this.unreadWarnings = 0;
    this._localSeq = 0;
    this.channelUnread = {
      system: 0,
      task: 0,
      git: 0,
      ports: 0,
      terminal: 0,
      diagnostics: 0,
    };

    this._filterDebounceTimer = null;
    this._announceTimer = null;
    this._pendingAnnounceErrors = 0;
    this._pendingAnnounceWarnings = 0;

    this._initIcons();
    this._initEvents();

    this.client = new OutputClient({
      onRecords: (rs) => this._onRecords(rs),
      onReset: (info) => this._onReset(info),
      onState: (state) => this._onState(state),
      onDropped: (n) => this._onDropped(n),
    });

    if (this.view) {
      this.view.onPinnedChange = (pinned) => {
        if (this.jumpBtn) {
          this.jumpBtn.hidden = pinned;
        }
      };
    }
  }

  _initIcons() {
    if (this.timeBtn) {
      this.timeBtn.replaceChildren(createSvgIcon("clock", 14));
    }
    if (this.wrapBtn) {
      this.wrapBtn.replaceChildren(createSvgIcon("wrap", 14));
    }
    if (this.copyBtn) {
      this.copyBtn.replaceChildren(createSvgIcon("copy", 14));
    }
    if (this.saveBtn) {
      this.saveBtn.replaceChildren(createSvgIcon("download", 14));
    }
    if (this.clearBtn) {
      this.clearBtn.replaceChildren(createSvgIcon("trash", 14));
    }
  }

  _initEvents() {
    if (this.channelSelect) {
      this.channelSelect.addEventListener("change", (e) => {
        const ch = e.target.value;
        if (this.view) {
          this.view.filter.channel = ch;
          this.view.renderAll();
        }
        if (ch === "all") {
          for (const k of Object.keys(this.channelUnread)) {
            this.channelUnread[k] = 0;
          }
        } else if (this.channelUnread[ch] !== undefined) {
          this.channelUnread[ch] = 0;
        }
        this._updateChannelSelectBadges();
      });
    }

    if (this.levelSelect) {
      this.levelSelect.addEventListener("change", (e) => {
        if (this.view) {
          this.view.filter.minLevel = e.target.value;
          this.view.renderAll();
        }
      });
    }

    if (this.filterInput) {
      this.filterInput.addEventListener("input", (e) => {
        if (this._filterDebounceTimer) {
          clearTimeout(this._filterDebounceTimer);
        }
        this._filterDebounceTimer = setTimeout(() => {
          if (this.view) {
            this.view.filter.text = e.target.value.trim().toLowerCase();
            this.view.renderAll();
          }
        }, 150);
      });
    }

    if (this.panelEl) {
      this.panelEl.addEventListener("keydown", (e) => {
        if (e.key === "End") {
          e.preventDefault();
          this.jumpToLatest();
        } else if ((e.ctrlKey || e.metaKey) && (e.key === "a" || e.key === "A")) {
          // Select only log contents
          if (this.view && this.view.el) {
            e.preventDefault();
            const range = document.createRange();
            range.selectNodeContents(this.view.el);
            const sel = window.getSelection();
            if (sel) {
              sel.removeAllRanges();
              sel.addRange(range);
            }
          }
        } else if (e.key === "Escape") {
          e.preventDefault();
          if (this.tabEl) {
            this.tabEl.focus();
          }
        }
      });
    }
  }

  start() {
    window.DeskAIOutput = this;
    this.client.connect();
  }

  log(channel, level, text) {
    this._localSeq = (this._localSeq || 0) - 1;
    const rec = {
      seq: this._localSeq,
      ts: Date.now(),
      channel: channel || "system",
      level: level || "info",
      text: String(text),
    };
    this._onRecords([rec]);
  }

  _onRecords(records) {
    if (!this.view) return;
    this.view.writeRecords(records);

    const activeChan = (this.channelSelect && this.channelSelect.value) || "all";
    let channelCountChanged = false;
    for (const r of records) {
      if (this.channelUnread[r.channel] !== undefined) {
        if (!this.isActive || (activeChan !== "all" && activeChan !== r.channel)) {
          this.channelUnread[r.channel] = (this.channelUnread[r.channel] || 0) + 1;
          channelCountChanged = true;
        }
      }
    }
    if (channelCountChanged) {
      this._updateChannelSelectBadges();
    }

    let errCount = 0;
    let warnCount = 0;
    for (const r of records) {
      if (r.level === "error") errCount++;
      else if (r.level === "warn") warnCount++;
    }

    if (this.isActive) {
      if (errCount > 0 || warnCount > 0) {
        this._pendingAnnounceErrors += errCount;
        this._pendingAnnounceWarnings += warnCount;
        this._scheduleAnnouncement();
      }
    } else {
      if (errCount > 0 || warnCount > 0) {
        this.unreadErrors += errCount;
        this.unreadWarnings += warnCount;
        this._updateTabIndicator();
      }
    }
  }

  _updateChannelSelectBadges() {
    if (!this.channelSelect) return;
    const baseNames = {
      all: "All",
      system: "System",
      task: "Task",
      git: "Git",
      ports: "Ports",
      terminal: "Terminal",
      diagnostics: "Diagnostics",
    };
    let anyUnread = false;
    for (const opt of this.channelSelect.options) {
      const val = opt.value;
      const base = baseNames[val] || val;
      const count = this.channelUnread[val] || 0;
      if (count > 0) {
        opt.textContent = `${base} (${count})`;
        anyUnread = true;
      } else {
        opt.textContent = base;
      }
    }
    this.channelSelect.classList.toggle("has-unread", anyUnread);
  }

  _scheduleAnnouncement() {
    if (this._announceTimer) {
      clearTimeout(this._announceTimer);
    }
    this._announceTimer = setTimeout(() => {
      const parts = [];
      if (this._pendingAnnounceErrors > 0) {
        parts.push(
          `${this._pendingAnnounceErrors} new error${this._pendingAnnounceErrors !== 1 ? "s" : ""}`
        );
      }
      if (this._pendingAnnounceWarnings > 0) {
        parts.push(
          `${this._pendingAnnounceWarnings} warning${this._pendingAnnounceWarnings !== 1 ? "s" : ""}`
        );
      }
      if (parts.length > 0) {
        announce(`${parts.join(", ")} in Output`);
      }
      this._pendingAnnounceErrors = 0;
      this._pendingAnnounceWarnings = 0;
    }, 1000);
  }

  _updateTabIndicator() {
    if (!this.tabEl) return;
    let badge = this.tabEl.querySelector(".tab-badge");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "tab-badge";
      this.tabEl.appendChild(badge);
    }

    const total = this.unreadErrors + this.unreadWarnings;
    if (total > 0) {
      badge.hidden = false;
      badge.textContent = String(total);
      if (this.unreadErrors > 0) {
        badge.classList.add("has-errors");
        badge.classList.remove("has-warnings");
        this.tabEl.setAttribute(
          "aria-label",
          `Output, ${this.unreadErrors} new error${this.unreadErrors !== 1 ? "s" : ""}`
        );
      } else {
        badge.classList.add("has-warnings");
        badge.classList.remove("has-errors");
        this.tabEl.setAttribute(
          "aria-label",
          `Output, ${this.unreadWarnings} new warning${this.unreadWarnings !== 1 ? "s" : ""}`
        );
      }
    } else {
      badge.hidden = true;
      badge.textContent = "";
      badge.classList.remove("has-errors", "has-warnings");
      this.tabEl.setAttribute("aria-label", "Output");
    }
  }

  onShow() {
    this.isActive = true;
    this.unreadErrors = 0;
    this.unreadWarnings = 0;
    this._updateTabIndicator();
    const activeChan = (this.channelSelect && this.channelSelect.value) || "all";
    if (activeChan === "all") {
      for (const k of Object.keys(this.channelUnread)) {
        this.channelUnread[k] = 0;
      }
    } else if (this.channelUnread[activeChan] !== undefined) {
      this.channelUnread[activeChan] = 0;
    }
    this._updateChannelSelectBadges();
    if (this.jumpBtn && this.view) {
      this.jumpBtn.hidden = this.view.pinned;
    }
  }

  onHide() {
    this.isActive = false;
  }

  _onReset({ restarted, missed }) {
    if (restarted) {
      if (this.view) this.view.clear();
      this.log("system", "info", "[DeskAI System] Server restarted; previous log discarded.");
    } else if (missed > 0) {
      this.log("system", "warn", `${missed} earlier lines were discarded`);
    }
  }

  _onDropped(n) {
    this.log("system", "warn", `${n} lines were dropped (slow display)`);
  }

  _onState(state) {
    if (!this.statusEl) return;
    if (state === "streaming") {
      this.statusEl.hidden = true;
      this.statusEl.replaceChildren();
    } else if (state === "connecting") {
      this.statusEl.hidden = false;
      this.statusEl.textContent = "Connecting…";
    } else if (state === "reconnecting") {
      this.statusEl.hidden = false;
      this.statusEl.textContent = "Reconnecting…";
    } else if (state === "unavailable") {
      this.statusEl.hidden = false;
      this.statusEl.replaceChildren();
      const text = document.createTextNode("Output stream unavailable ");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "output-retry-btn";
      btn.dataset.action = "output-retry";
      btn.textContent = "Retry";
      btn.addEventListener("click", () => this.retry());
      this.statusEl.append(text, btn);
    }
  }

  retry() {
    this.client.retry();
  }

  toggleTime() {
    if (!this.view || !this.timeBtn) return;
    const cur = !!this.view.options.timestamps;
    const next = !cur;
    this.timeBtn.setAttribute("aria-pressed", String(next));
    this.view.setOptions({ timestamps: next });
  }

  toggleWrap() {
    if (!this.view || !this.wrapBtn) return;
    const cur = !!this.view.options.wrap;
    const next = !cur;
    this.wrapBtn.setAttribute("aria-pressed", String(next));
    this.view.setOptions({ wrap: next });
  }

  copyVisible() {
    if (!this.view || !this.view.el) return;
    const lines = [];
    const rows = this.view.el.querySelectorAll(".log-line");
    const showTime = !!(this.view && this.view.options && this.view.options.timestamps);
    for (const row of rows) {
      const time = showTime ? (row.querySelector(".log-time")?.textContent || "") : "";
      const chan = row.querySelector(".log-channel")?.textContent || "";
      const isTagVisible = row.classList.contains("log-warn") || row.classList.contains("log-error");
      const tag = isTagVisible ? (row.querySelector(".log-level-tag")?.textContent || "") : "";
      const text = row.querySelector(".log-text")?.textContent || "";
      const parts = [];
      if (time) parts.push(time);
      if (chan) parts.push(chan);
      if (tag) parts.push(tag);
      if (text) parts.push(text);
      lines.push(parts.join(" "));
    }
    const fullText = lines.join("\n");
    if (window.NativeBridge && typeof window.NativeBridge.clipboardWrite === "function") {
      window.NativeBridge.clipboardWrite(fullText);
    } else if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(fullText).catch(() => {});
    }
    announce(`Copied ${lines.length} lines`);
  }

  async saveLog() {
    if (!this.view || !this.view.el) return;
    const lines = [];
    const rows = this.view.el.querySelectorAll(".log-line");
    const showTime = !!(this.view && this.view.options && this.view.options.timestamps);
    for (const row of rows) {
      const time = showTime ? (row.querySelector(".log-time")?.textContent || "") : "";
      const chan = row.querySelector(".log-channel")?.textContent || "";
      const isTagVisible = row.classList.contains("log-warn") || row.classList.contains("log-error");
      const tag = isTagVisible ? (row.querySelector(".log-level-tag")?.textContent || "") : "";
      const text = row.querySelector(".log-text")?.textContent || "";
      const parts = [];
      if (time) parts.push(time);
      if (chan) parts.push(`[${chan}]`);
      if (tag) parts.push(`[${tag}]`);
      if (text) parts.push(text);
      lines.push(parts.join(" "));
    }
    const content = lines.join("\n");
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const timestampStr = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const filename = `deskai-output-${timestampStr}.log`;

    // 1. Desktop native dialog (PyWebView bridge)
    if (
      window.pywebview &&
      window.pywebview.api &&
      typeof window.pywebview.api.save_file_dialog === "function"
    ) {
      try {
        const res = await NativeBridge.saveFileDialog(filename);
        if (res && res.status === "ok" && res.path) {
          const writeRes = await NativeBridge.writeFile(res.path, content);
          if (writeRes && writeRes.status === "ok") {
            const baseName = res.path.split("/").pop().split("\\").pop();
            announce(`Saved ${lines.length} lines to ${baseName}`);
            if (window.ExplorerManager && typeof window.ExplorerManager.refresh === "function") {
              await window.ExplorerManager.refresh();
            }
            return;
          } else if (writeRes && writeRes.message) {
            console.error("Failed to write log file:", writeRes.message);
            announce(`Save failed: ${writeRes.message}`);
            return;
          }
        } else if (res && res.status === "error" && res.message) {
          console.error("Save file dialog error:", res.message);
          announce(`Save failed: ${res.message}`);
          return;
        } else if (res && res.status === "cancelled") {
          return;
        }
      } catch (err) {
        console.error("Native save failed, falling back to browser download:", err);
      }
    }

    // 2. Browser fallback (Blob URL download) for standard browser tabs & headless test runners
    try {
      const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      announce(`Saved ${lines.length} lines to ${filename}`);
    } catch (err) {
      console.error("Failed to save output:", err);
    }
  }

  async navigateToFile(relOrAbsFile, line = 1, col = 1) {
    if (!relOrAbsFile) return;
    let fullPath = relOrAbsFile;
    const isAbs = /^(?:\/|[a-zA-Z]:[/\\])/.test(relOrAbsFile);
    if (!isAbs) {
      const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
      if (root) {
        const cleanRoot = root.replace(/\/+$/, "");
        const cleanRel = relOrAbsFile.replace(/^\/+/, "");
        fullPath = `${cleanRoot}/${cleanRel}`;
      }
    }

    if (window.EditorManager && typeof window.EditorManager.openAt === "function") {
      await window.EditorManager.openAt(fullPath, line, col);
    } else if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
      await window.EditorManager.openFile(fullPath);
    }
    announce(`Opened ${relOrAbsFile} at line ${line}`);
  }

  clear() {
    if (this.view) {
      this.view.clear();
    }
    announce("Output cleared");
  }

  jumpToLatest() {
    if (this.view) {
      this.view.pinned = true;
      const scroller = this.view.scrollContainer;
      if (scroller) {
        scroller.scrollTop = scroller.scrollHeight;
      }
    }
    if (this.jumpBtn) {
      this.jumpBtn.hidden = true;
    }
  }
}
