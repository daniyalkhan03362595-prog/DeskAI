# High-Level Design (HLD): Inline Chat Renaming (Quick & Native)

**Document ID:** `ORX-HLD-INLINE-CHAT-RENAMING-V2`  
**Version:** `2.0` (Synchronized with LLD V2 & Vanilla JS Studio Architecture)  
**Target Codebase:** `DeskAI` (`src/deskai/static/index.html`)  
**Status:** Approved  
**Date:** October 24, 2026  

---

## 1. Architectural Overview & Objective
* **Current State:** When a user clicks the rename icon (`✎`) or right-clicks a chat session in the sidebar, the native browser `window.prompt()` dialog is triggered. On WebKitGTK / PyWebView, this halts the UI execution thread, breaks the dark-theme aesthetic, and exposes the internal `http://127.0.0.1:8765` URL and session token.
* **Target State:** Clicking the rename icon transforms the specific session row (`.task-item-row`) directly into an in-place controlled `<input>` field with inline Confirm (`✓`) and Cancel (`✕`) action buttons, completely eliminating blocking browser prompts.

---

## 2. Component Architecture & UI State Machine

Each chat session item (`.task-item-row`) rendered inside `#projectsTree` operates across three distinct states: **View Mode**, **Edit Mode**, and **Persisting Mode**.

| State | CSS Selector | UI Elements Visible | User Actions Available |
| :--- | :--- | :--- | :--- |
| **View Mode (Default)** | `.task-item-row` | Chat icon, Static Title (`<span>`), Rename (`✎`), Delete (`🗑`) | Click row (Switch session), Click `✎` or Right-Click (Enter Edit Mode) |
| **Edit Mode (Active)** | `.task-item-row.is-editing` | Chat icon, Auto-focused `<input>`, Confirm (`✓`), Cancel (`✕`) | Type new title, Press `Enter` / Click `✓` (Save), Press `Esc` / Click `✕` (Cancel), Click outside (Auto-save if valid, else Cancel) |
| **Persisting Mode** | `.task-item-row.is-editing.is-saving` | Chat icon, Disabled `<input>`, Muted action buttons | Input locked while `saveProjects()` completes to prevent duplicate submissions |

### Singleton State Model
Because the UI uses Vanilla JavaScript DOM re-rendering (`renderProjectsTree()`), a singleton state object (`activeInlineRename`) manages the lifecycle across the sidebar:
* `projectId: string | null` — Tracks the parent project of the session being edited.
* `sessionId: string | null` — Tracks which chat session is currently in Edit Mode (enforcing a single-edit lock across all projects).
* `originalTitle: string` — Preserves the pre-edit title for validation comparisons and failure rollbacks.
* `originalManuallyRenamed: boolean` — Preserves the pre-edit `manuallyRenamed` flag for accurate state rollback on network error.
* `isSaving: boolean` — Concurrency lock preventing duplicate persistence calls.
* `isClosing: boolean` — Synchronous guard preventing `onblur` race conditions when the `<input>` is unmounted during `Enter` or `Esc` key handling.

---

## 3. End-to-End Interaction & Data Flow

```text
[User Clicks Rename Icon (✎) or Right-Clicks Row]
       │
       ▼
[Set activeInlineRename = { projectId, sessionId, originalTitle, ... }]
       │
       ▼
[renderProjectsTree() Renders <input> + requestAnimationFrame Auto-Focus & Select]
       │
       ├──► (User presses 'Esc' or clicks '✕') 
       │           └──► [Set isClosing = true ──► Clear State & Restore Original View Mode]
       │
       └──► (User presses 'Enter', clicks '✓', or clicks outside [Blur])
                   │
                   ▼
         [Validation Check: Is sanitizedTitle empty or equal to originalTitle?]
          ├─ Yes ──► [Cancel Edit & Revert to View Mode]
          └─ No  ──► [Optimistic UI Update: Update sess.title & Header Breadcrumb]
                            │
                            ▼
                     [Dispatch Async saveProjects() (POST /api/projects/save)]
                      ├─ 200 OK ──► [Finalize Commit & Return to View Mode]
                      └─ Error  ──► [Rollback sess.title & manuallyRenamed + Re-render Header/Sidebar]
```

### Step-by-Step Execution
1. **Trigger:** User clicks the edit icon (`✎`) or right-clicks a session row. `event.stopPropagation()` and `event.preventDefault()` prevent triggering `switchSession()` or the native browser context menu.
2. **Focus & Selection:** `renderProjectsTree()` renders the row in `.is-editing` mode. Using `requestAnimationFrame`, the `<input>` is automatically focused and its text selected.
3. **Commit (Save):** User presses `Enter`, clicks `✓`, or clicks outside after typing a valid new name.
4. **Synchronization & Rollback Safety:**
   * Backup values (`originalTitle` and `originalManuallyRenamed`) are captured into local variables before resetting the UI state.
   * The sidebar and top breadcrumb header (`updateHeaderTitles()`) update immediately (Optimistic UI).
   * `await saveProjects()` persists the updated project tree to `localStorage` and the local backend (`POST /api/projects/save`).
   * If persistence fails, the local backup variables restore the exact prior state and re-synchronize the header and sidebar.

---

## 4. API & Backend Persistence Contract

In Desktop AI Studio, chat sessions are stored within the hierarchical `projects` state tree and persisted via the unified project save pipeline:

* **Frontend Persistence Function:** `await saveProjects()`
* **Backend Endpoint:** `POST /api/projects/save` (authenticated via session token)
* **Session Mutation Payload (within Project Object):**
  ```json
  {
    "id": "sess_1729729812345",
    "title": "New Task Session Name",
    "manuallyRenamed": true
  }
  ```
* **Validation Rules:**
  * Input enforces `maxlength="100"`.
  * After applying `.trim()`, the string length must be between `1` and `100` characters.
  * If the trimmed string is empty or identical to `originalTitle`, the network call is bypassed and the row cleanly exits Edit Mode.

---

## 5. Edge Cases & UX Safeguards

* **Blur vs. Enter/Esc Race Condition Guard:** Removing a focused `<input>` from the DOM during `renderProjectsTree()` synchronously fires `onblur`. The `activeInlineRename.isClosing` flag ensures `handleInlineRenameBlur()` immediately exits if a commit or cancel is already in progress.
* **Blur vs. Action Button Click Guard:** Both Confirm (`✓`) and Cancel (`✕`) buttons bind `onmousedown="event.preventDefault()"` so clicking them does not steal focus from the `<input>` and prematurely trigger `onblur`.
* **Event Bubbling Containment:** Clicking inside the `<input>` or pressing keys (`Space`, `Enter`, `Escape`, letter hotkeys) invokes `event.stopPropagation()` so global Studio shortcuts or session-switching handlers are never triggered.
* **Single Edit Lock:** Initiating rename on Session B while Session A is open in Edit Mode automatically overwrites `activeInlineRename`, cleanly reverting Session A and opening Session B.
* **XSS & Text Overflow Protection:** Session titles are assigned via DOM `.value` in Edit Mode and escaped via `escapeHtml()` in View Mode, with CSS `text-overflow: ellipsis; white-space: nowrap; overflow: hidden;` preventing sidebar width expansion.

---

## 6. Styling & Theme Specifications

Design tokens aligned with the Desktop AI Studio dark theme (`src/studio/ui/index.html`):

* **Row Container (`.task-item-row.is-editing`):**
  * Background: `var(--bg-surface, #1e2024)`
  * Border: `1px solid #3b82f6` with subtle focus ring `0 0 0 1px rgba(59, 130, 246, 0.25)`
  * Padding: `3px 6px` (maintains exact vertical rhythm with standard rows to prevent layout jump)
* **Input Field (`.inline-rename-input`):**
  * Background: `#141517` (transitions to `#101113` on focus)
  * Border: `1px solid #475569` (transitions to `#3b82f6` on focus)
  * Typography: `12px`, `line-height: 18px`, `color: var(--text-main, #e2e8f0)`
* **Action Buttons (`.inline-action-btn`):**
  * Dimensions: `20px × 20px`, `border-radius: 4px`, default color `var(--text-muted, #94a3b8)`
  * Confirm (`✓`) Hover: `#4ade80` (green accent) with `rgba(74, 222, 128, 0.1)` background
  * Cancel (`✕`) Hover: `#f87171` (red accent) with `rgba(248, 113, 113, 0.1)` background
