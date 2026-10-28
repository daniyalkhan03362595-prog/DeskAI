# High-Level Design (HLD): Window Control Bar

**Document ID:** `ORX-HLD-WINDOW-CONTROL-BAR-V1`  
**Version:** `1.0` (Core Layer 1 UI Component Architecture)  
**Parent Component:** `UI features components`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/js/app.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
**Status:** Approved  
**Date:** October 28, 2026  

---

## 1. Architectural Overview & Objective

The **Window Control Bar** (`#appHeader`, `role="banner"`) is the uppermost persistent horizontal navigation and native window control strip of DeskAI. Operating across frameless native desktop containers (`easygui` / `pywebview` on Windows, Linux, and macOS), it reconciles custom web-based IDE aesthetics with native operating system window management.

It orchestrates four dedicated subcomponents:
1. **`app-branding-title` (`.app-logo`):** Displays application branding and identity (`⚡ DeskAI`), non-interactive drag pass-through, and WAI-ARIA banner landmark accessibility.
2. **`workspace-branch-pill` (`.workspace-pill`):** Reactive pill tracking workspace directory status and active Git branch, dynamically synchronizing across filesystem state transitions.
3. **`window-drag-region` (`.pywebview-drag-region`):** Full-header drag surface enabling multi-platform native window movement across monitors and double-click window maximize/restore toggling.
4. **`native-window-buttons` (`.window-controls`):** Triad of minimize, maximize/restore, and guarded-exit close buttons protecting unsaved editor state and background terminal subprocesses.

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ #appHeader.app-header.pywebview-drag-region [role="banner"] [-webkit-app-region: drag]      │
│ ┌───────────────────────────────────────────────┐ ┌───────────────────────────────────────┐ │
│ │ .header-left                                  │ │ .header-right .window-controls        │ │
│ │ ┌───────────────────┐ ┌─────────────────────┐ │ │ [role="group" aria-label="Controls"]  │ │
│ │ │ ⚡ DeskAI         │ │ DeskAI / main       │ │ │ ┌─────────┐ ┌─────────┐ ┌───────────┐ │ │
│ │ │ (.app-logo)       │ │ (.workspace-pill)   │ │ │ │   ─     │ │   □     │ │    ✕      │ │ │
│ │ │ [drag pass-thru]  │ │ [no-drag]           │ │ │ │ minimize│ │ maximize│ │ win-close │ │ │
│ │ └───────────────────┘ └─────────────────────┘ │ │ └─────────┘ └─────────┘ └───────────┘ │ │
│ └───────────────────────────────────────────────┘ └───────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Subcomponent Hierarchy & Responsibilities

| Subcomponent | DOM Selector | Primary Responsibilities | Interaction Region |
| :--- | :--- | :--- | :--- |
| **App Branding Title** | `.app-logo` | Brand recognition (`⚡ DeskAI`), visual anchor, screen reader announcement. | `drag` (pass-through) |
| **Workspace Branch Pill** | `#headerWorkspacePill` | Displays `Workspace / Branch`, reacts to `store` path and git changes. | `no-drag` |
| **Window Drag Region** | `#appHeader` | Cross-platform dragging (Wayland/X11 GDK, Win32 `WM_NCLBUTTONDOWN`, Cocoa), double-click maximize. | `drag` |
| **Native Window Buttons** | `.window-controls` | Window state toggling (`minimize`, `maximize`), guarded exit confirmation on dirty state. | `no-drag` |

---

## 3. Data Flow & Inter-Component Integration

```mermaid
flowchart TD
    subgraph Frontend["Frontend Runtime (ES6 Modules)"]
        Store["State Store (store.js)<br/>workspace.rootPath, workspace.branch, dirtyTabs"]
        Pill["WorkspacePillController (app.js)"]
        Events["Action Delegator (events.js)"]
        Modal["Confirm Exit Dialog (#confirmModal)"]
        Terminal["DeskAITerminal (terminal.js)"]
    end

    subgraph NativeBridge["Bridge Layer (bridge.js)"]
        NB_Git["NativeBridge.getGitBranch()"]
        NB_Win["NativeBridge.windowControl()"]
    end

    subgraph Backend["Python DesktopBridgeAPI (api.py)"]
        Py_Git["get_git_branch(target_path)"]
        Py_Win["window_control(action)"]
        Py_TM["TerminalManager.has_active_sessions()"]
    end

    Store -->|Subscribe: rootPath, branch| Pill
    Pill -->|Query branch| NB_Git
    NB_Git -->|IPC| Py_Git

    Events -->|Click win-minimize / win-maximize| NB_Win
    Events -->|Click win-close (close_request)| NB_Win
    NB_Win -->|Check dirty & sessions| Py_Win
    Py_Win -->|Query active| Py_TM

    NB_Win -->|canClose = false| Events
    Events -->|Dirty / Terminals Active| Modal
    Modal -->|confirm-exit| Terminal
    Modal -->|confirm-exit| NB_Win
```

---

## 4. Accessibility & WAI-ARIA Architecture

1. **Header Landmark:** `<header>` container with `role="banner"`.
2. **Interactive Controls Grouping:** `.window-controls` marked with `role="group"` and `aria-label="Window Controls"`.
3. **Workspace Status:** `.workspace-pill` marked with `role="status"` and accessible `aria-label`.
4. **Keyboard Operability:** Sequential tab navigation skips non-interactive branding (`.app-logo`), traverses interactive `.workspace-pill`, and reaches `.win-min`, `.win-max`, and `.win-close`.
5. **Escape Sequences:** Modals and focus traps honor `Escape` key cancellations.

---

## 5. Non-Negotiable Constraints Compliance

1. **Zero Raw Hex Colors:** All color definitions strictly leverage `tokens.css` (`--bg-header`, `--text-muted`, `--text-primary`, `--bg-hover`, `--color-danger`, `--color-amber`).
2. **Zero `innerHTML` for Dynamic Content:** Dynamic pill text and modal dialogues rely exclusively on `.textContent` and `document.createElement`.
3. **Zero Framework Runtime:** Vanilla ES6 modules only; zero external runtime UI dependencies.
4. **High-Performance Dragging:** CSS `-webkit-app-region: drag` coupled with selective `-webkit-app-region: no-drag` prevents mouse event contention.
