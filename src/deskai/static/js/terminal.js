/**
 * Terminal & Output Log View Components for DeskAI Bottom Drawer.
 * Interfaces with dedicated /ws/terminal/{id} WebSocket transport.
 * Built with vanilla ES modules, vendored xterm.js, and WCAG 2.1 AA accessibility.
 */

import { NativeBridge } from "./bridge.js";

const MAX_LOG_LINES = 10000;
const ANSI_REGEX = /\x1B(?:\][^\x07\x1B]*(?:\x07|\x1B\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])/g;
function getStyleNonce() {
  if (typeof document === "undefined") return "";
  const meta = document.querySelector('meta[name="csp-nonce"]');
  return meta ? meta.getAttribute("content") || "" : "";
}

// Hook document.createElement to ensure dynamic <style> elements created by xterm.js
// receive the CSP nonce required by strict style-src 'nonce-...'.
// Rationale: xterm.js has no constructor option or API to supply a style nonce for its
// internal character measurement and theme styles.
if (typeof document !== "undefined" && !document._deskaiStyleNonceHooked) {
  document._deskaiStyleNonceHooked = true;
  const origCreate = document.createElement.bind(document);
  document.createElement = function(tagName, options) {
    const el = origCreate(tagName, options);
    if (tagName && typeof tagName === "string" && tagName.toLowerCase() === "style") {
      const nonce = getStyleNonce();
      if (nonce) {
        el.nonce = nonce;
      }
    }
    return el;
  };
}

/**
 * Reads token-driven theme colors from CSS variables in tokens.css.
 * Zero hex literals in JavaScript.
 */
function getTerminalTheme() {
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  return {
    background: cs.getPropertyValue("--terminal-bg").trim(),
    foreground: cs.getPropertyValue("--terminal-fg").trim(),
    cursor: cs.getPropertyValue("--terminal-cursor").trim(),
    selectionBackground: cs.getPropertyValue("--terminal-selection").trim(),
    black: cs.getPropertyValue("--ansi-black").trim(),
    red: cs.getPropertyValue("--ansi-red").trim(),
    green: cs.getPropertyValue("--ansi-green").trim(),
    yellow: cs.getPropertyValue("--ansi-yellow").trim(),
    blue: cs.getPropertyValue("--ansi-blue").trim(),
    magenta: cs.getPropertyValue("--ansi-magenta").trim(),
    cyan: cs.getPropertyValue("--ansi-cyan").trim(),
    white: cs.getPropertyValue("--ansi-white").trim(),
    brightBlack: cs.getPropertyValue("--ansi-bright-black").trim(),
    brightRed: cs.getPropertyValue("--ansi-bright-red").trim(),
    brightGreen: cs.getPropertyValue("--ansi-bright-green").trim(),
    brightYellow: cs.getPropertyValue("--ansi-bright-yellow").trim(),
    brightBlue: cs.getPropertyValue("--ansi-bright-blue").trim(),
    brightMagenta: cs.getPropertyValue("--ansi-bright-magenta").trim(),
    brightCyan: cs.getPropertyValue("--ansi-bright-cyan").trim(),
    brightWhite: cs.getPropertyValue("--ansi-bright-white").trim(),
  };
}

function getStoredScreenReaderMode() {
  try {
    return localStorage.getItem("deskai-terminal-sr-mode") === "true";
  } catch (e) {
    return false;
  }
}

function setStoredScreenReaderMode(enabled) {
  try {
    localStorage.setItem("deskai-terminal-sr-mode", enabled ? "true" : "false");
  } catch (e) {
    // Ignore localStorage errors (e.g. storage access blocked)
  }
}

function announce(message) {
  const el = document.getElementById("screenReaderAnnouncer");
  if (el) {
    el.textContent = message;
  }
}

function updateTabStatus(isRunning) {
  const tab = document.getElementById("tab-terminal");
  if (!tab) return;
  tab.textContent = "";
  const label = document.createElement("span");
  label.textContent = "Terminal";
  tab.appendChild(label);

  if (isRunning) {
    const space = document.createTextNode(" ");
    const chip = document.createElement("span");
    chip.className = "terminal-status-chip running";
    chip.setAttribute("aria-label", "(running)");
    chip.textContent = "●";
    tab.appendChild(space);
    tab.appendChild(chip);
  }
}

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
    this.term = null;
    this.fitAddon = null;
    this.ws = null;
    this._sessionId = null;
    this.isInitialized = false;
    this.isOpening = false;
    this.resizeRafId = 0;
    this.encoder = new TextEncoder();
    this.hasExited = false;
    this.reconnectAttempts = 0;
    this.lastCloseCode = 1006;
    this.isActive = false;
    this.isIdle = true;
  }

  get sessionId() {
    return this._sessionId;
  }

  set sessionId(val) {
    this._sessionId = val;
    if (val) {
      this.hasExited = false;
    }
    this._updateKillButtonState();
  }

  init() {
    if (!this.host || !window.Terminal) return;

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

    this.term.open(this.host);

    // Idle state: do not capture Tab until activated by user (Enter or Click)
    const helperTa = this.host ? this.host.querySelector("textarea") : null;
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

    // Setup Screen Reader Toggle
    const srCheckbox = document.getElementById("terminalSrToggle");
    if (srCheckbox) {
      srCheckbox.checked = srMode;
      srCheckbox.addEventListener("change", () => {
        const isEnabled = srCheckbox.checked;
        setStoredScreenReaderMode(isEnabled);
        if (this.term && this.term.options) {
          this.term.options.screenReaderMode = isEnabled;
        }
      });
    }

    // Setup Kill Terminal Button
    const killBtn = document.getElementById("terminalKillBtn");
    if (killBtn) {
      killBtn.addEventListener("click", () => this.kill());
    }
    this._updateKillButtonState();

    // Keyboard & Clipboard Event Interceptor
    this.term.attachCustomKeyEventHandler((e) => {
      const isCmd = isMac ? e.metaKey : e.ctrlKey;
      const key = e.key.toLowerCase();

      // Idle State: Tab moves on normally and is not captured
      if (key === "tab") {
        if (!this.isActive || this.isIdle) {
          return false;
        }
      }

      // WCAG Keyboard Trap Escape: Esc or Ctrl+Shift+M moves focus to Terminal tab
      if (key === "escape" || (isCmd && e.shiftKey && key === "m")) {
        if (e.type === "keydown") {
          e.preventDefault();
          this.deactivate();
          const tab = document.getElementById("tab-terminal");
          if (tab) tab.focus();
        }
        return false;
      }

      // Copy: Ctrl+Shift+C (or Cmd+C on Mac when selection exists)
      if (isCmd && ((e.shiftKey && key === "c") || (isMac && key === "c"))) {
        if (this.term.hasSelection()) {
          if (e.type === "keydown") {
            e.preventDefault();
            navigator.clipboard.writeText(this.term.getSelection());
          }
          return false;
        }
      }

      // Allow terminal to consume Ctrl+S, Ctrl+W, Ctrl+Enter without app shortcuts triggering
      if (isCmd && (key === "s" || key === "w" || key === "enter")) {
        return true;
      }

      // Boot UX: Press Enter to start a shell if no session active yet
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

    // Data input from keystrokes
    this.term.onData((data) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(this.encoder.encode(data));
      } else {
        if (!this.sessionId && !this.isOpening && !this.hasExited) {
          if (data === "\r" || data === "\n") {
            this.startSession();
            return;
          }
        }
        if (!this.hasExited && this.sessionId) {
          this.showConnectionLostBanner(this.lastCloseCode || 1006);
        }
      }
    });

    // Binary input handler
    this.term.onBinary((data) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        const bytes = new Uint8Array(data.length);
        for (let i = 0; i < data.length; i++) {
          bytes[i] = data.charCodeAt(i) & 255;
        }
        this.ws.send(bytes);
      } else {
        if (!this.hasExited && this.sessionId) {
          this.showConnectionLostBanner(this.lastCloseCode || 1006);
        }
      }
    });

    // Enter on panel focuses terminal textarea
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

    // Host click starts session if not yet started
    if (this.host) {
      this.host.addEventListener("click", () => {
        if (!this.sessionId && !this.isOpening && !this.hasExited) {
          this.startSession();
        }
      });
    }

    if (!this.sessionId) {
      this.term.writeln("\r\nPress Enter or click to start a shell\r\n");
    }

    this.isInitialized = true;
  }

  activate() {
    this.isActive = true;
    this.isIdle = false;
    const helperTa = this.host ? this.host.querySelector("textarea") : null;
    if (helperTa) {
      helperTa.setAttribute("tabindex", "0");
      helperTa.focus();
    }
    const hint = document.querySelector(".terminal-footer-hint");
    if (hint) {
      hint.textContent = "Focus trapped in shell. Press Esc or Ctrl+Shift+M to exit";
      hint.classList.add("focus-trapped");
    }
    announce("Terminal active. Press Escape or Ctrl+Shift+M to move focus out.");
    if (!this.sessionId && !this.isOpening && !this.hasExited) {
      this.startSession();
    }
  }

  deactivate() {
    this.isActive = false;
    this.isIdle = true;
    const helperTa = this.host ? this.host.querySelector("textarea") : null;
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

  async startSession() {
    if (this.isOpening) return;
    this.isOpening = true;

    try {
      this.hasExited = false;
      this.reconnectAttempts = 0;
      this.removeExitBanner();
      const dims = this.getDimensions();
      const res = await NativeBridge.terminalOpen(dims.cols, dims.rows);

      if (res && res.status === "ok" && res.session_id) {
        this.sessionId = res.session_id;
        this._updateKillButtonState();
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

  connectWebSocket(sessionId) {
    if (this.ws) {
      try {
        this.ws.close();
      } catch (err) {
        // Ignored
      }
      this.ws = null;
    }

    const host = window.location.host;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${host}/ws/terminal/${sessionId}`;

    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      updateTabStatus(true);
      this.removeExitBanner();
      this.fit();
    };

    this.ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          const frame = jsonSafeParse(event.data);
          if (frame && frame.type === "exit") {
            this.handleProcessExit(frame.code ?? 0);
          } else if (frame && frame.type === "error") {
            console.warn("[Terminal] Transport error frame:", frame);
          }
        } catch (err) {
          // Ignored
        }
      } else if (event.data instanceof ArrayBuffer) {
        if (this.term) {
          this.term.write(new Uint8Array(event.data));
        }
      }
    };

    this.ws.onclose = (event) => {
      const code = event ? event.code : 1006;
      this.lastCloseCode = code;

      if (this.hasExited) {
        return;
      }

      if (code === 4429 && this.reconnectAttempts < 3) {
        this.reconnectAttempts++;
        setTimeout(() => {
          if (this.sessionId && !this.hasExited) {
            this.connectWebSocket(this.sessionId);
          }
        }, 300);
        return;
      }

      updateTabStatus(false);
      this.showConnectionLostBanner(code);
    };

    this.ws.onerror = (err) => {
      console.warn("[Terminal] WebSocket error:", err);
    };
  }

  handleProcessExit(code) {
    this.hasExited = true;
    this._updateKillButtonState();
    updateTabStatus(false);
    if (!this.host) return;
    this.removeExitBanner();

    const banner = document.createElement("div");
    banner.className = "terminal-status-banner";

    const msgSpan = document.createElement("span");
    msgSpan.textContent = `Terminal exited with code ${code}.`;

    const restartBtn = document.createElement("button");
    restartBtn.className = "terminal-restart-btn";
    restartBtn.setAttribute("data-action", "restart-terminal");
    restartBtn.textContent = "Restart terminal";
    restartBtn.addEventListener("click", () => {
      const oldSessionId = this.sessionId;
      this.sessionId = null;
      if (oldSessionId) {
        NativeBridge.terminalClose(oldSessionId);
      }
      if (this.term) this.term.reset();
      this.startSession();
    });

    banner.appendChild(msgSpan);
    banner.appendChild(restartBtn);
    this.host.appendChild(banner);

    announce(`Terminal exited with code ${code}`);
  }

  async kill() {
    if (this.sessionId) {
      const id = this.sessionId;
      this.sessionId = null;
      this.hasExited = true;
      this._updateKillButtonState();
      await NativeBridge.terminalClose(id);
      this.handleProcessExit(137);
    }
  }

  showConnectionLostBanner(code = 1006) {
    updateTabStatus(false);
    if (!this.host) return;
    this.removeExitBanner();

    const banner = document.createElement("div");
    banner.className = "terminal-status-banner connection-lost";

    const msgSpan = document.createElement("span");
    msgSpan.textContent = `Connection lost (code ${code}).`;

    const reconnectBtn = document.createElement("button");
    reconnectBtn.className = "terminal-restart-btn";
    reconnectBtn.setAttribute("data-action", "reconnect-terminal");
    reconnectBtn.textContent = "Reconnect";
    reconnectBtn.addEventListener("click", () => {
      this.removeExitBanner();
      if (this.term) this.term.reset();
      if (this.sessionId) {
        this.connectWebSocket(this.sessionId);
      } else {
        this.startSession();
      }
    });

    banner.appendChild(msgSpan);
    banner.appendChild(reconnectBtn);
    this.host.appendChild(banner);

    announce(`Connection lost (code ${code})`);
  }

  removeExitBanner() {
    if (this.host) {
      const banner = this.host.querySelector(".terminal-status-banner");
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
      if (!this.isPanelVisible() || !this.fitAddon || !this.term) return;

      try {
        this.fitAddon.fit();
        const cols = this.term.cols;
        const rows = this.term.rows;

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: "resize", cols, rows }));
        }
      } catch (err) {
        // Ignored
      }
    });
  }

  destroy() {
    this.hasExited = true;
    updateTabStatus(false);
    this.removeExitBanner();
    if (this.sessionId) {
      NativeBridge.terminalClose(this.sessionId);
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {
        // Ignored
      }
      this.ws = null;
    }
    if (this.term) {
      this.term.dispose();
      this.term = null;
    }
    this.sessionId = null;
    this._updateKillButtonState();
    this.isInitialized = false;
  }

  _updateKillButtonState() {
    const killBtn = document.getElementById("terminalKillBtn");
    if (!killBtn) return;
    const isAlive = Boolean(this.sessionId && !this.hasExited);
    if (isAlive) {
      killBtn.removeAttribute("disabled");
      killBtn.setAttribute("aria-disabled", "false");
      killBtn.title = "Kill active terminal session";
    } else {
      killBtn.setAttribute("disabled", "disabled");
      killBtn.setAttribute("aria-disabled", "true");
      killBtn.title = "No active terminal session";
    }
  }
}

function jsonSafeParse(str) {
  try {
    return JSON.parse(str);
  } catch (e) {
    return null;
  }
}
