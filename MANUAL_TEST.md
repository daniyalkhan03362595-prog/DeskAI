# DeskAI Layer 1 - Manual Verification Guide

This guide details manual test procedures for platform-specific window behaviors (Wayland, X11, and Windows) that cannot be executed in headless automated CI runners.

---

## 1. Environment Matrix

| Platform | Window Manager / Compositor | Backend |
| :--- | :--- | :--- |
| **Linux (Wayland)** | GNOME Shell / Sway / KDE Wayland | WebKit2GTK + GDK Wayland |
| **Linux (X11)** | Xorg + Mutter / XFWM4 / Openbox | WebKit2GTK + GDK X11 |
| **Windows** | DWM (Windows 10 / 11) | WebView2 (Chromium) + Win32 HWND |

---

## 2. Test Procedures

### Test Case 1: Frameless Title Bar Dragging
* **Objective:** Verify dragging the custom title bar moves the window smoothly without jitter or click-stealing.
* **Steps:**
  1. Launch DeskAI via `deskai`.
  2. Click and hold the mouse on an empty area of the custom top title bar (`#appHeader`).
  3. Drag the cursor across the screen.
* **Expected Result:**
  - **Linux (Wayland/X11):** GDK `begin_move_drag` is invoked and the compositor initiates interactive window movement.
  - **Windows:** ctypes dispatches `WM_NCLBUTTONDOWN` with `HTCAPTION (2)` to native HWND after `ReleaseCapture()`; DWM smoothly moves the window.

### Test Case 2: Double-Click Title Bar Maximize / Restore
* **Objective:** Ensure double-clicking the title bar toggles maximize state without accidentally triggering a move drag.
* **Steps:**
  1. Rapidly double-click on `#appHeader`.
* **Expected Result:**
  - The window maximizes to fill the monitor.
  - The timestamp / rapid click guard prevents `drag_start` from hijacking the second click.
  - Double-clicking again restores the window to its original geometry.

### Test Case 3: Perimeter & Corner Edge Resizing
* **Objective:** Verify the >= 6px perimeter resize handles allow resizing in all 8 directions.
* **Steps:**
  1. Hover cursor over window edges (top, bottom, left, right) and corners (top-left, top-right, bottom-left, bottom-right).
  2. Observe cursor styling changes (`ns-resize`, `ew-resize`, `nwse-resize`, `nesw-resize`).
  3. Click and drag each handle inward and outward.
* **Expected Result:**
  - **Linux:** GDK `begin_resize_drag` handles interactive resizing per compass direction.
  - **Windows:** ctypes dispatches `WM_NCLBUTTONDOWN` with hit-test codes (`10`-`17`) according to the edge. Window resizes smoothly.

### Test Case 4: Maximize State Handles Concealment
* **Objective:** Verify resize handles do not capture clicks when the window is maximized.
* **Steps:**
  1. Maximize window.
  2. Click at the absolute screen borders.
* **Expected Result:**
  - `.window-resize-handles` are hidden via CSS `display: none !important;` under maximized state, preventing spurious resize attempts.

### Test Case 5: Dirty Buffer Exit Flow & Single Confirmation
* **Objective:** Verify closing the application with dirty buffers prompts only ONCE and does not loop or re-prompt on destroy.
* **Steps:**
  1. Launch DeskAI and type text into an editor buffer to mark it dirty (indicated by the amber dot).
  2. Click the title bar close button (`✕` / `win-close`).
* **Expected Result:**
  - An in-app confirmation modal (`#confirmModal`) or native confirmation dialog appears asking: *"You have unsaved changes in your workspace. Are you sure you want to exit?"*
  - Clicking **Cancel** keeps the app running with dirty buffers intact.
  - Clicking **Discard & Exit** closes the window immediately.
  - No second dialog or confirmation prompt is triggered during window teardown.
