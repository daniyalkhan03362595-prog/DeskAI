/**
 * ProblemsView: Safe DOM renderer and keyboard interaction model for the Problems panel.
 * Strictly adheres to zero innerHTML, WCAG 2.1 AA, and roving tabindex.
 */

import { createSvgIcon } from "../icons.js";

const LABEL = {
  error: "Error",
  warning: "Warning",
  info: "Info"
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function renderGroups(container, grouped, ui) {
  if (!grouped || grouped.size === 0) {
    const emptySpan = el("span", "problems-empty", "No problems have been detected in the workspace.");
    container.replaceChildren(emptySpan);
    return;
  }

  const frag = document.createDocumentFragment();
  let firstItem = true;

  for (const [file, items] of grouped) {
    const group = el("div", "problems-group");
    const isCollapsed = ui.collapsed.has(file);
    const groupId = `pg-${ui.idFor(file)}`;

    const head = el("button", "problems-file");
    head.type = "button";
    head.setAttribute("aria-expanded", String(!isCollapsed));
    head.setAttribute("aria-controls", groupId);
    head.dataset.file = file;
    head.tabIndex = firstItem && !ui.focusedId ? 0 : -1;
    if (firstItem && !ui.focusedId) firstItem = false;

    const chevron = createSvgIcon(isCollapsed ? "chevron-right" : "chevron-down", 12, "problems-chevron");
    const nameSpan = el("span", "problems-file-name", file);
    const countSpan = el("span", "problems-file-count", `(${items.length})`);
    head.append(chevron, nameSpan, countSpan);

    const list = el("ul", "problems-list");
    list.id = groupId;
    list.setAttribute("role", "list");
    list.hidden = isCollapsed;

    if (!isCollapsed) {
      for (const d of items) {
        const row = renderItem(d, ui, firstItem);
        if (firstItem && !ui.focusedId) firstItem = false;
        list.appendChild(row);
      }
    }

    group.append(head, list);
    frag.appendChild(group);
  }

  container.replaceChildren(frag);

  // Restore focus if a previous element was focused
  if (ui.focusedId) {
    const target = container.querySelector(`[data-id="${ui.focusedId}"]`) ||
                   container.querySelector(`[data-file="${ui.focusedId}"]`);
    if (target) {
      // Set roving tabindex
      container.querySelectorAll(".problems-file, .problem-item").forEach(b => { b.tabIndex = -1; });
      target.tabIndex = 0;
      target.focus();
    }
  }
}

function renderItem(d, ui, isFirst) {
  const li = el("li", "problems-row");
  li.setAttribute("role", "listitem");

  const btn = el("button", `problem-item severity-${d.severity}`);
  btn.type = "button";
  btn.dataset.id = d.id;
  btn.dataset.file = d.file;

  const startLine = d.range ? d.range.startLine : d.start_line || 1;
  const startCol = d.range ? d.range.startCol : d.start_col || 1;

  btn.dataset.line = String(startLine);
  btn.dataset.col = String(startCol);

  const sevLabel = LABEL[d.severity] || "Problem";
  const sourceCode = d.code ? `${d.source} ${d.code}` : d.source;

  btn.setAttribute(
    "aria-label",
    `${sevLabel}, ${d.message}, ${d.file} line ${startLine} column ${startCol}, source ${d.source}`
  );
  btn.setAttribute("title", d.message);

  btn.tabIndex = ui.focusedId === d.id ? 0 : -1;

  const icon = createSvgIcon(d.severity, 14, `problem-severity-icon severity-${d.severity}`);
  const sevSpan = el("span", "problem-severity", sevLabel);
  const msgSpan = el("span", "problem-message", d.message);
  const srcSpan = el("span", "problem-source", sourceCode);
  const locSpan = el("span", "problem-location", `[${startLine}, ${startCol}]`);

  btn.append(icon, sevSpan, msgSpan, srcSpan, locSpan);
  li.appendChild(btn);
  return li;
}

/**
 * Attaches keyboard navigation (roving tabindex) and click handlers to the problems view container.
 */
export function initViewKeyboardAndClicks(container, ui, onNavigate) {
  container.addEventListener("click", (e) => {
    const itemBtn = e.target.closest(".problem-item");
    if (itemBtn) {
      const file = itemBtn.dataset.file;
      const line = parseInt(itemBtn.dataset.line, 10) || 1;
      const col = parseInt(itemBtn.dataset.col, 10) || 1;
      ui.focusedId = itemBtn.dataset.id;
      setRovingTabindex(container, itemBtn);
      if (typeof onNavigate === "function") {
        onNavigate(file, line, col);
      }
      return;
    }

    const fileBtn = e.target.closest(".problems-file");
    if (fileBtn) {
      const file = fileBtn.dataset.file;
      ui.toggleCollapse(file);
      ui.focusedId = file;
      return;
    }
  });

  container.addEventListener("keydown", (e) => {
    const active = document.activeElement;
    if (!active || !container.contains(active)) return;

    const items = Array.from(container.querySelectorAll(".problems-file, .problem-item:not([hidden])"));
    const currentIndex = items.indexOf(active);
    if (currentIndex === -1) return;

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        const next = items[currentIndex + 1] || items[0];
        setRovingTabindex(container, next);
        next.focus();
        break;
      }
      case "ArrowUp": {
        e.preventDefault();
        const prev = items[currentIndex - 1] || items[items.length - 1];
        setRovingTabindex(container, prev);
        prev.focus();
        break;
      }
      case "ArrowRight": {
        if (active.classList.contains("problems-file")) {
          e.preventDefault();
          const file = active.dataset.file;
          if (ui.collapsed.has(file)) {
            ui.toggleCollapse(file);
          }
        }
        break;
      }
      case "ArrowLeft": {
        e.preventDefault();
        if (active.classList.contains("problems-file")) {
          const file = active.dataset.file;
          if (!ui.collapsed.has(file)) {
            ui.toggleCollapse(file);
          }
        } else if (active.classList.contains("problem-item")) {
          const group = active.closest(".problems-group");
          const head = group ? group.querySelector(".problems-file") : null;
          if (head) {
            setRovingTabindex(container, head);
            head.focus();
          }
        }
        break;
      }
      case "Home": {
        e.preventDefault();
        if (items.length > 0) {
          setRovingTabindex(container, items[0]);
          items[0].focus();
        }
        break;
      }
      case "End": {
        e.preventDefault();
        if (items.length > 0) {
          const last = items[items.length - 1];
          setRovingTabindex(container, last);
          last.focus();
        }
        break;
      }
      case "Enter":
      case " ": {
        e.preventDefault();
        active.click();
        break;
      }
      case "Escape": {
        e.preventDefault();
        const tabBtn = document.getElementById("tab-problems");
        if (tabBtn) tabBtn.focus();
        break;
      }
    }
  });
}

function setRovingTabindex(container, targetEl) {
  container.querySelectorAll(".problems-file, .problem-item").forEach(el => {
    el.tabIndex = -1;
  });
  if (targetEl) {
    targetEl.tabIndex = 0;
  }
}
