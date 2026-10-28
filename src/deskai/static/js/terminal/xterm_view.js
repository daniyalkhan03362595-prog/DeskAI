/**
 * Xterm View Adapter Module.
 * Configures xterm.js instance, theme tokens, WCAG 2.1 AA screen reader support,
 * and keyboard trap navigation.
 */

function getStyleNonce() {
  if (typeof document === "undefined") return "";
  const meta = document.querySelector('meta[name="csp-nonce"]');
  return meta ? meta.getAttribute("content") || "" : "";
}

// Hook document.createElement to ensure dynamic <style> elements created by xterm.js
// receive the CSP nonce required by strict style-src 'nonce-...'.
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

export function getTerminalTheme() {
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

export function getStoredScreenReaderMode() {
  try {
    return localStorage.getItem("deskai-terminal-sr-mode") === "true";
  } catch (e) {
    return false;
  }
}

export function setStoredScreenReaderMode(enabled) {
  try {
    localStorage.setItem("deskai-terminal-sr-mode", enabled ? "true" : "false");
  } catch (e) {
    // Ignore localStorage errors
  }
}

export function announce(message) {
  const el = document.getElementById("screenReaderAnnouncer");
  if (el) {
    el.textContent = message;
  }
}

export function updateTabStatus(isRunning) {
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
