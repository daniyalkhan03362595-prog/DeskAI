/**
 * Terminal & Output Log View Components for DeskAI Bottom Drawer.
 * Built with vanilla ES modules, vendored xterm.js, and WCAG 2.1 AA accessibility.
 */

import { NativeBridge } from "./bridge.js";
import { createSvgIcon } from "./icons.js";
import { TerminalTransport } from "./terminal/transport.js";
import {
  getTerminalTheme,
  getStoredScreenReaderMode,
  setStoredScreenReaderMode,
  announce,
  updateTabStatus
} from "./terminal/xterm_view.js";

const MAX_LOG_LINES = 10000;
const ANSI_REGEX = /\x1B(?:\][^\x07\x1B]*(?:\x07|\x1B\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])/g;

export { getTerminalTheme, announce, updateTabStatus };

/**
 * Batched, memory-capped, text-safe LogView for read-only channel outputs (#channelOutput).
 */
export class LogView {
  constructor(element) {
    this.el = element;
    this.queue = [];
    this.rafId = 0;
    this.lineCount = 0;
    this.pinned = true;

    const scroller = this.scrollContainer;
    if (scroller) {
      scroller.addEventListener("scroll", () => {
        const dist = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
        this.pinned = dist < 40;
      });
    }
  }

  get scrollContainer() {
    return (this.el && this.el.closest) ? (this.el.closest(".drawer-content") || this.el) : this.el;
  }

  write(text, className = "") {
    if (!text) return;
    const cleanText = String(text).replace(ANSI_REGEX, "");
    this.queue.push({ text: cleanText, className });
    if (!this.rafId) {
      this.rafId = requestAnimationFrame(() => this._flush());
    }
  }

  _flush() {
    this.rafId = 0;
    if (!this.el) return;

    const items = this.queue.splice(0);
    const frag = document.createDocumentFragment();

    for (const item of items) {
      const span = document.createElement("span");
      if (item.className && ["log-error", "log-warn", "log-info", "log-debug"].includes(item.className)) {
        span.className = item.className;
      }
      span.textContent = item.text;
      frag.appendChild(span);

      const newlines = (item.text.match(/\n/g) || []).length || 1;
      this.lineCount += newlines;
    }

    this.el.appendChild(frag);

    while (this.lineCount > MAX_LOG_LINES && this.el.firstChild) {
      const first = this.el.firstChild;
      const count = (first.textContent.match(/\n/g) || []).length || 1;
      this.lineCount -= count;
      first.remove();
    }

    if (this.pinned) {
      const scroller = this.scrollContainer;
      if (scroller) {
        scroller.scrollTop = scroller.scrollHeight;
      }
    }
  }

  clear() {
    this.queue = [];
    this.lineCount = 0;
    if (this.el) {
      this.el.textContent = "";
    }
    const scroller = this.scrollContainer;
    if (scroller) {
      scroller.scrollTop = 0;
    }
  }
}

/**
 * Interactive Terminal Manager backing #terminalHost.
 */
export class TerminalView {
  constructor() {
    this.host = document.getElementById("terminalHost");
    this.tabsSidebar = document.getElementById("terminalTabsSidebar");
    this.sessions = [];
    this.activeSessionId = null;
    this.MAX_SESSIONS = 6;
    this.primaryContainer = null;

    this.term = null;
    this.fitAddon = null;
    this.transport = new TerminalTransport({
      onOpen: () => {
        updateTabStatus(true);
        this.removeExitBanner();
        this.fit();
      },
      onData: (bytes) => {
        if (this.term) this.term.write(bytes);
      },
      onExit: (code) => {
        this.handleProcessExit(code);
      },
      onClose: (code) => {
        updateTabStatus(false);
        this.showConnectionLostBanner(code);
      },
      isExited: () => this.hasExited,
    });
    this._sessionId = null;
    this.isInitialized = false;
    this.isOpening = false;
    this.resizeRafId = 0;
    this.hasExited = false;
    this.lastCloseCode = 1006;
    this.isActive = false;
    this.isIdle = true;
    this.isAuthPending = false;
    this._killBtnBound = false;
    this._srBound = false;
  }

  get ws() {
    return this.transport ? this.transport.ws : null;
  }

  set ws(val) {
    if (this.transport) {
      this.transport.ws = val;
    }
  }

  get reconnectAttempts() {
    return this.transport ? this.transport.reconnectAttempts : 0;
  }

  set reconnectAttempts(val) {
    if (this.transport) {
      this.transport.reconnectAttempts = val;
    }
  }

  get sessionId() {
    return this._sessionId;
  }

  set sessionId(val) {
    this._sessionId = val;
    if (val) {
      this.hasExited = false;
      this.activeSessionId = val;
    }
    this._updateKillButtonState();
  }

  init() {
    if (!this.host || !window.Terminal) return;
    this.tabsSidebar = document.getElementById("terminalTabsSidebar");

    const session1Container = document.createElement("div");
    session1Container.className = "terminal-instance active";
    session1Container.id = "term-inst-initial";
    this.host.appendChild(session1Container);
    this.primaryContainer = session1Container;

    const theme = getTerminalTheme();
    const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
    const srMode = getStoredScreenReaderMode();

    this.term = new window.Terminal({
      cursorBlink: true,
      fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
      fontSize: 12,
      lineHeight: 1.25,
      scrollback: MAX_LOG_LINES,
      screenReaderMode: srMode,
      theme,
      linkHandler: {
        activate: (event, text) => {
          NativeBridge.openExternalUrl(text);
        },
      },
    });

    if (window.FitAddon && window.FitAddon.FitAddon) {
      this.fitAddon = new window.FitAddon.FitAddon();
      this.term.loadAddon(this.fitAddon);
    }

    this.term.open(session1Container);

    const helperTa = session1Container.querySelector("textarea");
    if (helperTa) {
      helperTa.setAttribute("tabindex", "-1");
    }

    if (this.host) {
      this.host.addEventListener("click", () => {
        this.activate();
      });
      this.host.addEventListener("keydown", (e) => {
        if (!this.isActive && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          this.activate();
        }
      });
    }

    const srCheckbox = document.getElementById("terminalSrToggle");
    if (srCheckbox && !this._srBound) {
      srCheckbox.checked = srMode;
      srCheckbox.addEventListener("change", () => {
        const isEnabled = srCheckbox.checked;
        setStoredScreenReaderMode(isEnabled);
        if (this.term && this.term.options) {
          this.term.options.screenReaderMode = isEnabled;
        }
        this.sessions.forEach((s) => {
          if (s.term && s.term.options) {
            s.term.options.screenReaderMode = isEnabled;
          }
        });
      });
      this._srBound = true;
    }

    const killBtn = document.getElementById("terminalKillBtn");
    if (killBtn && !this._killBtnBound) {
      killBtn.addEventListener("click", () => this.kill());
      this._killBtnBound = true;
    }

    this._bindPrimaryTermEvents(isMac);

    const panel = document.getElementById("terminalPanel");
    if (panel) {
      panel.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && document.activeElement === panel) {
          e.preventDefault();
          this.term.focus();
          if (!this.sessionId && !this.isOpening && !this.hasExited) {
            this.startSession();
          }
        }
      });
    }

    if (!this.sessionId) {
      this.term.writeln("\r\nPress Enter or click to start a shell\r\n");
    }

    this._updateKillButtonState();
    this._updateNewTerminalButtonState();
    this.renderTabsList();
    this.isInitialized = true;
  }

  async copySelection(term) {
    if (!term) return;
    const text = term.getSelection();
    if (!text) return;

    let copied = false;
    try {
      if (NativeBridge && typeof NativeBridge.clipboardWrite === "function") {
        const res = await NativeBridge.clipboardWrite(text);
        if (res && res.status === "ok") {
          copied = true;
        }
      }
    } catch (e) {
      console.warn("[Terminal] NativeBridge.clipboardWrite error:", e);
    }

    if (!copied) {
      try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          await navigator.clipboard.writeText(text);
          copied = true;
        }
      } catch (e) {
        console.warn("[Terminal] navigator.clipboard.writeText error:", e);
      }
    }

    if (!copied) {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        ta.style.top = "-9999px";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        ta.remove();
        copied = true;
      } catch (e) {
        console.error("[Terminal] execCommand copy error:", e);
      }
    }
  }

  async pasteClipboard(term) {
    if (!term) return;
    let text = "";

    try {
      if (NativeBridge && typeof NativeBridge.clipboardRead === "function") {
        const res = await NativeBridge.clipboardRead();
        if (res && res.status === "ok" && typeof res.text === "string" && res.text.length > 0) {
          text = res.text;
        }
      }
    } catch (e) {
      console.warn("[Terminal] NativeBridge.clipboardRead error:", e);
    }

    if (!text) {
      try {
        if (navigator.clipboard && typeof navigator.clipboard.readText === "function") {
          text = await navigator.clipboard.readText();
        }
      } catch (e) {
        console.warn("[Terminal] navigator.clipboard.readText error:", e);
      }
    }

    if (text) {
      term.paste(text);
    }
  }

  _bindPrimaryTermEvents(isMac) {
    this.term.attachCustomKeyEventHandler((e) => {
      if (this.isAuthPending) {
        return false;
      }

      const isCmd = isMac ? e.metaKey : e.ctrlKey;
      const key = e.key.toLowerCase();

      if (key === "tab") {
        if (!this.isActive || this.isIdle) {
          return false;
        }
      }

      if (key === "escape" || (isCmd && e.shiftKey && key === "m")) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.deactivate();
          const tab = document.getElementById("tab-terminal");
          if (tab) tab.focus();
        }
        return false;
      }

      if (isCmd && ((e.shiftKey && key === "a") || (isMac && key === "a"))) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.term.selectAll();
        }
        return false;
      }

      if (isCmd && ((e.shiftKey && key === "c") || (isMac && key === "c"))) {
        if (this.term.hasSelection()) {
          if (e.type === "keydown") {
            e.preventDefault();
            this.copySelection(this.term);
          }
          return false;
        }
      }

      if (isCmd && ((e.shiftKey && key === "v") || (isMac && key === "v"))) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.pasteClipboard(this.term);
        }
        return false;
      }

      if (isCmd && (key === "s" || key === "w" || key === "enter")) {
        return true;
      }

      if (!this.sessionId && !this.isOpening && !this.hasExited) {
        if (key === "enter") {
          if (e.type === "keydown") {
            this.activate();
          }
          return false;
        }
      }

      return true;
    });

    this.term.onData((data) => {
      if (this.isAuthPending) return;
      const sent = this.transport.sendData(data);
      if (!sent) {
        if (!this.sessionId && !this.isOpening && !this.hasExited) {
          if (data === "\r" || data === "\n") {
            this.startSession();
            return;
          }
        }
        if (!this.hasExited && this.sessionId) {
          this.showConnectionLostBanner(this.transport.lastCloseCode || 1006);
        }
      }
    });

    this.term.onBinary((data) => {
      if (this.isAuthPending) return;
      const bytes = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        bytes[i] = data.charCodeAt(i) & 255;
      }
      const sent = this.transport.sendData(bytes);
      if (!sent && !this.hasExited && this.sessionId) {
        this.showConnectionLostBanner(this.transport.lastCloseCode || 1006);
      }
    });
  }

  activate() {
    this.isActive = true;
    this.isIdle = false;
    const helperTa = this.host ? this.host.querySelector(".terminal-instance.active textarea, textarea") : null;
    if (helperTa) {
      helperTa.setAttribute("tabindex", "0");
      if (!this.isAuthPending) {
        helperTa.focus();
      }
    }
    const hint = document.querySelector(".terminal-footer-hint");
    if (hint) {
      hint.textContent = "Focus trapped in shell. Press Esc or Ctrl+Shift+M to exit";
      hint.classList.add("focus-trapped");
    }
    announce("Terminal active. Press Escape or Ctrl+Shift+M to move focus out.");
    if (!this.sessionId && !this.isOpening && !this.hasExited && !this.isAuthPending) {
      this.startSession();
    }
  }

  deactivate() {
    this.isActive = false;
    this.isIdle = true;
    const helperTa = this.host ? this.host.querySelector(".terminal-instance.active textarea, textarea") : null;
    if (helperTa) {
      helperTa.setAttribute("tabindex", "-1");
    }
    const hint = document.querySelector(".terminal-footer-hint");
    if (hint) {
      hint.textContent = "Ctrl+Shift+M: Move focus out";
      hint.classList.remove("focus-trapped");
    }
    announce("Terminal focus released. Press Tab to navigate.");
  }

  async onTabShown() {
    if (!this.isInitialized) {
      this.init();
    }
    if (!this.sessionId && !this.isOpening && this.isActive) {
      await this.startSession();
    } else {
      this.fit();
    }
  }

  async startSession(confirmed = false) {
    if (this.isOpening) return;
    this.isOpening = true;

    try {
      this.hasExited = false;
      this.transport.reconnectAttempts = 0;
      this.removeExitBanner();
      const dims = this.getDimensions();
      const res = await NativeBridge.terminalOpen(dims.cols, dims.rows, confirmed, true);

      if (res && res.status === "auth_required") {
        this.showAuthPrompt(res.workspace || "DeskAI");
        return;
      }

      this.removeAuthPrompt();

      if (res && res.status === "ok" && res.session_id) {
        this.sessionId = res.session_id;
        this.activeSessionId = res.session_id;
        const isWin = navigator.platform && navigator.platform.toUpperCase().includes("WIN");
        const shellName = isWin ? "cmd" : "bash";
        const sessionObj = {
          id: res.session_id,
          name: shellName,
          term: this.term,
          fitAddon: this.fitAddon,
          transport: this.transport,
          containerEl: this.primaryContainer,
          hasExited: false,
        };
        this.sessions = [sessionObj];

        this._updateKillButtonState();
        this._updateNewTerminalButtonState();
        this.renderTabsList();

        if (this.term) this.term.reset();
        updateTabStatus(true);
        this.connectWebSocket(this.sessionId);
        announce("Terminal started");
      } else {
        const errorMsg = res && res.message ? res.message : "Failed to open terminal session";
        if (this.term) {
          this.term.writeln(`\r\n\x1b[31m[DeskAI] ${errorMsg}\x1b[0m\r\n`);
        }
      }
    } catch (e) {
      console.error("[Terminal] Session open error:", e);
    } finally {
      this.isOpening = false;
    }
  }

  async newSession() {
    if (this.sessions.length >= this.MAX_SESSIONS) {
      announce("Maximum 6 terminal sessions reached");
      return;
    }

    if (!this.isInitialized) {
      this.init();
    }

    if (this.sessions.length === 0 && !this.sessionId && !this.isOpening) {
      await this.startSession(true);
      return;
    }

    await this._spawnAdditionalSession();
  }

  async _spawnAdditionalSession() {
    if (this.sessions.length >= this.MAX_SESSIONS) {
      announce("Maximum 6 terminal sessions reached");
      return;
    }

    const dims = this.getDimensions();
    const res = await NativeBridge.terminalOpen(dims.cols, dims.rows, true, true);
    if (!res || res.status !== "ok" || !res.session_id) {
      const errorMsg = res && res.message ? res.message : "Failed to spawn new terminal session";
      if (this.term) {
        this.term.writeln(`\r\n\x1b[31m[DeskAI] ${errorMsg}\x1b[0m\r\n`);
      }
      return;
    }

    const isWin = navigator.platform && navigator.platform.toUpperCase().includes("WIN");
    const shellName = isWin ? "cmd" : "bash";
    const name = shellName;

    const sessionObj = this._createSessionInstance(res.session_id, name);
    this.sessions.push(sessionObj);
    this.switchSession(res.session_id);
    sessionObj.transport.connect(res.session_id);

    this.renderTabsList();
    this._updateKillButtonState();
    this._updateNewTerminalButtonState();
    announce(`New terminal session created: ${name}`);
  }

  _createSessionInstance(sessionId, name) {
    const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
    const theme = getTerminalTheme();
    const srMode = getStoredScreenReaderMode();

    const container = document.createElement("div");
    container.className = "terminal-instance";
    container.id = `term-inst-${sessionId}`;
    this.host.appendChild(container);

    const term = new window.Terminal({
      cursorBlink: true,
      fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
      fontSize: 12,
      lineHeight: 1.25,
      scrollback: MAX_LOG_LINES,
      screenReaderMode: srMode,
      theme,
      linkHandler: {
        activate: (event, text) => {
          NativeBridge.openExternalUrl(text);
        },
      },
    });

    let fitAddon = null;
    if (window.FitAddon && window.FitAddon.FitAddon) {
      fitAddon = new window.FitAddon.FitAddon();
      term.loadAddon(fitAddon);
    }

    term.open(container);

    const helperTa = container.querySelector("textarea");
    if (helperTa) {
      helperTa.setAttribute("tabindex", "-1");
    }

    const sessionObj = {
      id: sessionId,
      name,
      term,
      fitAddon,
      transport: null,
      containerEl: container,
      hasExited: false,
    };

    const transport = new TerminalTransport({
      onOpen: () => {
        updateTabStatus(true);
        this.removeExitBanner(sessionObj);
        this.fit();
      },
      onData: (bytes) => {
        if (sessionObj.term) sessionObj.term.write(bytes);
      },
      onExit: (code) => {
        this.handleProcessExit(code, sessionObj);
      },
      onClose: (code) => {
        updateTabStatus(false);
        this.showConnectionLostBanner(code, sessionObj);
      },
      isExited: () => sessionObj.hasExited,
    });

    sessionObj.transport = transport;

    this._bindSessionTermEvents(sessionObj, isMac);

    return sessionObj;
  }

  _bindSessionTermEvents(sessionObj, isMac) {
    const term = sessionObj.term;
    const transport = sessionObj.transport;

    term.attachCustomKeyEventHandler((e) => {
      const isCmd = isMac ? e.metaKey : e.ctrlKey;
      const key = e.key.toLowerCase();

      if (key === "escape" || (isCmd && e.shiftKey && key === "m")) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.deactivate();
          const tab = document.getElementById("tab-terminal");
          if (tab) tab.focus();
        }
        return false;
      }

      if (isCmd && ((e.shiftKey && key === "a") || (isMac && key === "a"))) {
        if (e.type === "keydown") {
          e.preventDefault();
          term.selectAll();
        }
        return false;
      }

      if (isCmd && ((e.shiftKey && key === "c") || (isMac && key === "c"))) {
        if (term.hasSelection()) {
          if (e.type === "keydown") {
            e.preventDefault();
            this.copySelection(term);
          }
          return false;
        }
      }

      if (isCmd && ((e.shiftKey && key === "v") || (isMac && key === "v"))) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.pasteClipboard(term);
        }
        return false;
      }

      if (isCmd && (key === "s" || key === "w" || key === "enter")) {
        return true;
      }

      return true;
    });

    term.onData((data) => {
      const sent = transport.sendData(data);
      if (!sent && !sessionObj.hasExited && sessionObj.id) {
        this.showConnectionLostBanner(transport.lastCloseCode || 1006, sessionObj);
      }
    });

    term.onBinary((data) => {
      const bytes = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        bytes[i] = data.charCodeAt(i) & 255;
      }
      const sent = transport.sendData(bytes);
      if (!sent && !sessionObj.hasExited && sessionObj.id) {
        this.showConnectionLostBanner(transport.lastCloseCode || 1006, sessionObj);
      }
    });
  }

  switchSession(sessionId) {
    const targetSession = this.sessions.find((s) => s.id === sessionId);
    if (!targetSession) return;

    this.sessions.forEach((s) => {
      if (s.containerEl) {
        s.containerEl.classList.toggle("active", s.id === sessionId);
      }
    });

    this.activeSessionId = targetSession.id;
    this._sessionId = targetSession.id;
    this.term = targetSession.term;
    this.fitAddon = targetSession.fitAddon;
    this.transport = targetSession.transport;
    this.hasExited = targetSession.hasExited;

    this.renderTabsList();
    this._updateKillButtonState();
    this.fit();
    if (this.term) {
      try {
        this.term.refresh(0, this.term.rows - 1);
      } catch (err) {
        // Ignored
      }
      this.term.focus();
    }
    announce(`Switched to ${targetSession.name}`);
  }

  renderTabsList() {
    if (!this.tabsSidebar) {
      this.tabsSidebar = document.getElementById("terminalTabsSidebar");
    }
    if (!this.tabsSidebar) return;

    if (this.sessions.length <= 1) {
      this.tabsSidebar.classList.remove("is-visible");
      this.tabsSidebar.replaceChildren();
      return;
    }

    this.tabsSidebar.classList.add("is-visible");
    this.tabsSidebar.replaceChildren();

    this.sessions.forEach((session, idx) => {
      const isSelected = session.id === this.activeSessionId;
      const tabBtn = document.createElement("button");
      tabBtn.type = "button";
      tabBtn.className = `terminal-tab-item${isSelected ? " active" : ""}`;
      tabBtn.setAttribute("role", "tab");
      tabBtn.setAttribute("aria-selected", String(isSelected));
      tabBtn.setAttribute("tabindex", isSelected ? "0" : "-1");
      tabBtn.title = session.name;
      tabBtn.setAttribute("aria-label", `Terminal session ${idx + 1}: ${session.name}`);

      const titleSpan = document.createElement("span");
      titleSpan.className = "terminal-tab-title";
      titleSpan.appendChild(createSvgIcon("terminal", 12));
      const nameText = document.createElement("span");
      nameText.textContent = session.name;
      titleSpan.appendChild(nameText);
      tabBtn.appendChild(titleSpan);

      const closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "terminal-tab-close";
      closeBtn.setAttribute("data-action", "close-terminal-tab");
      closeBtn.setAttribute("aria-label", `Kill terminal ${idx + 1}: ${session.name}`);
      closeBtn.title = `Kill ${session.name}`;
      closeBtn.appendChild(createSvgIcon("close", 12));

      closeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.killSession(session.id);
      });

      tabBtn.appendChild(closeBtn);

      tabBtn.addEventListener("click", () => {
        this.switchSession(session.id);
      });

      this.tabsSidebar.appendChild(tabBtn);
    });
  }

  showAuthPrompt(workspaceName) {
    if (!this.host) return;
    this.removeAuthPrompt();
    this.isAuthPending = true;

    const banner = document.createElement("div");
    banner.className = "terminal-auth-banner";
    banner.id = "terminalAuthBanner";
    banner.setAttribute("role", "alertdialog");
    banner.setAttribute("aria-modal", "false");
    banner.setAttribute("aria-label", `Authorize terminal in ${workspaceName}`);

    const icon = createSvgIcon("terminal", 14, "terminal-auth-icon");
    banner.appendChild(icon);

    const textSpan = document.createElement("span");
    textSpan.className = "terminal-auth-text";
    textSpan.textContent = `Open a host shell in ${workspaceName}?`;
    banner.appendChild(textSpan);

    const actions = document.createElement("div");
    actions.className = "terminal-auth-actions";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "terminal-auth-btn terminal-auth-confirm";
    confirmBtn.setAttribute("data-action", "confirm-terminal-auth");
    confirmBtn.setAttribute("aria-label", "Authorize host shell");
    confirmBtn.title = "Authorize shell (Enter)";
    confirmBtn.appendChild(createSvgIcon("check", 14));

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "terminal-auth-btn terminal-auth-cancel";
    cancelBtn.setAttribute("data-action", "cancel-terminal-auth");
    cancelBtn.setAttribute("aria-label", "Cancel authorization");
    cancelBtn.title = "Cancel (Escape)";
    cancelBtn.appendChild(createSvgIcon("close", 14));

    actions.appendChild(confirmBtn);
    actions.appendChild(cancelBtn);
    banner.appendChild(actions);

    confirmBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.removeAuthPrompt();
      this.startSession(true);
    });

    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.cancelAuth();
    });

    banner.addEventListener("click", (e) => {
      e.stopPropagation();
    });

    banner.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Escape") {
        e.preventDefault();
        this.cancelAuth();
      } else if (e.key === "Enter") {
        e.preventDefault();
        this.removeAuthPrompt();
        this.startSession(true);
      } else if (e.key === "Tab") {
        if (e.shiftKey && document.activeElement === confirmBtn) {
          e.preventDefault();
          cancelBtn.focus();
        } else if (!e.shiftKey && document.activeElement === cancelBtn) {
          e.preventDefault();
          confirmBtn.focus();
        }
      }
    });

    this.host.appendChild(banner);
    confirmBtn.focus();
    announce(
      `Terminal authorization required: Open a host shell in ${workspaceName}? Press Enter to confirm, Escape to cancel.`
    );
  }

  cancelAuth() {
    this.removeAuthPrompt();
    this.deactivate();
    if (this.term) {
      this.term.writeln("\r\n\x1b[33m[DeskAI] Terminal authorization cancelled.\x1b[0m\r\n");
    }
    announce("Terminal authorization cancelled.");
    const tab = document.getElementById("tab-terminal");
    if (tab) tab.focus();
  }

  connectWebSocket(sessionId) {
    if (this.transport) {
      this.transport.connect(sessionId);
    }
  }

  handleProcessExit(code, sessionObj = null) {
    const targetSession = sessionObj || this.sessions.find((s) => s.id === this.activeSessionId);
    if (targetSession) {
      targetSession.hasExited = true;
    }
    if (!targetSession || targetSession.id === this.activeSessionId) {
      this.hasExited = true;
      this._updateKillButtonState();
      updateTabStatus(false);
    }

    const hostTarget = targetSession ? targetSession.containerEl : this.host;
    if (!hostTarget) return;

    this.removeExitBanner(targetSession);

    const banner = document.createElement("div");
    banner.className = "terminal-status-banner";

    const msgSpan = document.createElement("span");
    msgSpan.textContent = `Terminal exited with code ${code}.`;

    const restartBtn = document.createElement("button");
    restartBtn.className = "terminal-restart-btn";
    restartBtn.setAttribute("data-action", "restart-terminal");
    restartBtn.textContent = "Restart terminal";
    restartBtn.addEventListener("click", () => {
      if (targetSession) {
        this.killSession(targetSession.id);
        this.newSession();
      } else {
        const oldSessionId = this.sessionId;
        this.sessionId = null;
        if (oldSessionId) {
          NativeBridge.terminalClose(oldSessionId);
        }
        if (this.term) this.term.reset();
        this.startSession();
      }
    });

    banner.appendChild(msgSpan);
    banner.appendChild(restartBtn);
    hostTarget.appendChild(banner);

    announce(`Terminal exited with code ${code}`);
  }

  async kill(sessionId = null) {
    const targetId = sessionId || this.activeSessionId || this.sessionId;
    if (!targetId) return;
    await this.killSession(targetId);
  }

  async killSession(sessionId) {
    const idx = this.sessions.findIndex((s) => s.id === sessionId);
    if (idx === -1) {
      // Fallback for single/mock session (e.g. test_task5)
      this.sessionId = null;
      this.hasExited = true;
      this._updateKillButtonState();
      await NativeBridge.terminalClose(sessionId);
      this.handleProcessExit(137);
      return;
    }

    const session = this.sessions[idx];
    if (session.transport) {
      session.transport.close();
    }
    await NativeBridge.terminalClose(session.id);
    if (session.term) {
      session.term.dispose();
    }
    if (session.containerEl) {
      session.containerEl.remove();
    }

    this.sessions.splice(idx, 1);

    if (this.activeSessionId === sessionId) {
      if (this.sessions.length > 0) {
        const nextIdx = Math.min(idx, this.sessions.length - 1);
        this.switchSession(this.sessions[nextIdx].id);
      } else {
        this.activeSessionId = null;
        this.sessionId = null;
        this.hasExited = true;
        this._updateKillButtonState();
        this._updateNewTerminalButtonState();
        this.renderTabsList();
        this._createInitialIdleTerm();
      }
    } else {
      this.renderTabsList();
      this._updateKillButtonState();
      this._updateNewTerminalButtonState();
    }

    announce("Terminal session closed");
  }

  _createInitialIdleTerm() {
    if (this.primaryContainer) {
      this.primaryContainer.remove();
    }
    const session1Container = document.createElement("div");
    session1Container.className = "terminal-instance active";
    session1Container.id = "term-inst-idle";
    this.host.appendChild(session1Container);
    this.primaryContainer = session1Container;

    const theme = getTerminalTheme();
    const srMode = getStoredScreenReaderMode();
    const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;

    this.term = new window.Terminal({
      cursorBlink: true,
      fontFamily: 'var(--font-mono, "JetBrains Mono", monospace)',
      fontSize: 12,
      lineHeight: 1.25,
      scrollback: MAX_LOG_LINES,
      screenReaderMode: srMode,
      theme,
    });

    if (window.FitAddon && window.FitAddon.FitAddon) {
      this.fitAddon = new window.FitAddon.FitAddon();
      this.term.loadAddon(this.fitAddon);
    }

    this.term.open(session1Container);
    this.term.writeln("\r\nPress Enter or click to start a shell\r\n");

    const helperTa = session1Container.querySelector("textarea");
    if (helperTa) {
      helperTa.setAttribute("tabindex", "-1");
    }

    this._bindPrimaryTermEvents(isMac);
  }

  showConnectionLostBanner(code = 1006, sessionObj = null) {
    updateTabStatus(false);
    const hostTarget = sessionObj ? sessionObj.containerEl : this.host;
    if (!hostTarget) return;
    this.removeExitBanner(sessionObj);

    const banner = document.createElement("div");
    banner.className = "terminal-status-banner connection-lost";

    const msgSpan = document.createElement("span");
    msgSpan.textContent = `Connection lost (code ${code}).`;

    const reconnectBtn = document.createElement("button");
    reconnectBtn.className = "terminal-restart-btn";
    reconnectBtn.setAttribute("data-action", "reconnect-terminal");
    reconnectBtn.textContent = "Reconnect";
    reconnectBtn.addEventListener("click", () => {
      this.removeExitBanner(sessionObj);
      if (sessionObj) {
        if (sessionObj.term) sessionObj.term.reset();
        if (sessionObj.id) {
          sessionObj.transport.connect(sessionObj.id);
        }
      } else {
        if (this.term) this.term.reset();
        if (this.sessionId) {
          this.connectWebSocket(this.sessionId);
        } else {
          this.startSession();
        }
      }
    });

    banner.appendChild(msgSpan);
    banner.appendChild(reconnectBtn);
    hostTarget.appendChild(banner);

    announce(`Connection lost (code ${code})`);
  }

  removeExitBanner(sessionObj = null) {
    const hostTarget = sessionObj ? sessionObj.containerEl : this.host;
    if (hostTarget) {
      const banner = hostTarget.querySelector(".terminal-status-banner");
      if (banner) banner.remove();
    }
  }

  removeAuthPrompt() {
    this.isAuthPending = false;
    if (this.host) {
      const banner = this.host.querySelector(".terminal-auth-banner");
      if (banner) banner.remove();
    }
  }

  getDimensions() {
    if (this.fitAddon && this.isPanelVisible()) {
      try {
        const dims = this.fitAddon.proposeDimensions();
        if (dims && dims.cols && dims.rows) {
          return {
            cols: Math.max(10, Math.min(500, dims.cols)),
            rows: Math.max(2, Math.min(200, dims.rows)),
          };
        }
      } catch (e) {
        // Fallback
      }
    }
    return { cols: 80, rows: 24 };
  }

  isPanelVisible() {
    const panel = document.getElementById("terminalPanel");
    const drawer = document.getElementById("bottomDrawer");
    if (!panel || !drawer) return false;
    return !drawer.classList.contains("collapsed") && !panel.hasAttribute("hidden") && panel.classList.contains("active");
  }

  fit() {
    if (!this.isPanelVisible()) return;

    if (this.resizeRafId) cancelAnimationFrame(this.resizeRafId);
    this.resizeRafId = requestAnimationFrame(() => {
      this.resizeRafId = 0;
      if (!this.isPanelVisible()) return;

      const currentFit = this.fitAddon;
      const currentTerm = this.term;
      const currentTransport = this.transport;

      if (currentFit && currentTerm) {
        try {
          currentFit.fit();
          const cols = currentTerm.cols;
          const rows = currentTerm.rows;
          if (currentTransport) {
            currentTransport.sendResize(cols, rows);
          }
          currentTerm.refresh(0, currentTerm.rows - 1);
        } catch (err) {
          // Ignored
        }
      }
    });
  }

  destroy() {
    this.sessions.forEach((s) => {
      if (s.transport) s.transport.close();
      if (s.id) NativeBridge.terminalClose(s.id);
      if (s.term) s.term.dispose();
      if (s.containerEl) s.containerEl.remove();
    });
    this.sessions = [];
    this.activeSessionId = null;

    this.hasExited = true;
    this.isAuthPending = false;
    updateTabStatus(false);
    this.removeExitBanner();
    this.removeAuthPrompt();
    if (this.sessionId) {
      NativeBridge.terminalClose(this.sessionId);
    }
    if (this.transport) {
      this.transport.close();
    }
    if (this.term) {
      this.term.dispose();
      this.term = null;
    }
    this.sessionId = null;
    this._updateKillButtonState();
    this._updateNewTerminalButtonState();
    this.renderTabsList();
    this.isInitialized = false;
  }

  _updateKillButtonState() {
    const killBtn = document.getElementById("terminalKillBtn");
    const headerKillBtn = document.getElementById("btnKillTerminalHeader");
    const isAlive = Boolean(this.sessionId && !this.hasExited);

    [killBtn, headerKillBtn].forEach((btn) => {
      if (!btn) return;
      if (isAlive) {
        btn.removeAttribute("disabled");
        btn.setAttribute("aria-disabled", "false");
        btn.title = "Kill active terminal session";
      } else {
        btn.setAttribute("disabled", "disabled");
        btn.setAttribute("aria-disabled", "true");
        btn.title = "No active terminal session";
      }
    });

    this._updateNewTerminalButtonState();
  }

  _updateNewTerminalButtonState() {
    const newBtn = document.getElementById("btnNewTerminal");
    if (!newBtn) return;
    const isMax = this.sessions.length >= this.MAX_SESSIONS;
    if (isMax) {
      newBtn.setAttribute("disabled", "disabled");
      newBtn.setAttribute("aria-disabled", "true");
      newBtn.title = "Maximum 6 terminal sessions reached";
    } else {
      newBtn.removeAttribute("disabled");
      newBtn.setAttribute("aria-disabled", "false");
      newBtn.title = "New Terminal (Ctrl+Shift+`)";
    }
  }
}
