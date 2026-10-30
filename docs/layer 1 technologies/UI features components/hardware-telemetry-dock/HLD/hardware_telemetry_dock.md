# High-Level Design (HLD): Hardware Telemetry Dock

**Component Path:** `docs/layer 1 technologies/UI features components/hardware-telemetry-dock/`  
**DOM Target:** `#hardwareDock` inside `<aside class="sidebar-left" id="sidebarLeft">`  
**Standard:** WCAG 2.1 AA Compliant, Non-blocking Async Telemetry, Zero Layout Thrashing  

---

## 1. System Overview & Purpose

The **Hardware Telemetry Dock** (`#hardwareDock`) is a persistent status card anchored at the base of the Left Explorer Sidebar (`#sidebarLeft`). It provides developer-oriented, truthful, real-time visibility into the local workstation's hardware acceleration and memory utilization:

1. **GPU Acceleration Badge (`#teleGpuBadge`):** Real-time hardware accelerator detection, model reporting (`NVIDIA GeForce RTX 2070 SUPER`, Apple Silicon, AMD Radeon), and status indicator dot.
2. **GPU Temperature Indicator (`#teleGpuTempText`):** Real-time GPU core temperature in degrees Celsius with dynamic color-coding (`<60°C` cool/green, `60–79°C` warm/amber, `≥80°C` hot/danger).
3. **VRAM Usage Meter (`#teleVramText`, `#teleVramTrack`, `#teleVramFill`):** Resident VRAM consumption (`used / total GB`) with visual progress fill and accessibility bindings.
4. **Host RAM Indicator (`#teleRamText`):** Host system memory footprint (`used / total GB`).
5. **CPU Usage Percentage (`#teleCpuText`):** Live processor utilization (`xx.x%`) updated via non-blocking `psutil.cpu_percent`.
6. **CPU Temperature Indicator (`#teleCpuTempText`):** Live CPU package/core temperature in degrees Celsius with matching dynamic color-coding.

```
+-------------------------------------------------------------+
|                      sidebar-left                           |
| +---------------------------------------------------------+ |
| |                    explorer-container                   | |
| |  [EXPLORER]                           [Refresh][Collapse] |
| |  +---------------------------------------------------+  | |
| |  |               fileTreeViewport                    |  | |
| |  |  > src/                                           |  | |
| |  |    > deskai/                                      |  | |
| |  |      index.html                                   |  | |
| |  |      ... (Unblocked, scrolls cleanly above dock!) |  | |
| |  +---------------------------------------------------+  | |
| +---------------------------------------------------------+ |
| +---------------------------------------------------------+ |
| |                    hardware-dock                        | |
| |  GPU Acceleration     [🟢 NVIDIA RTX 2070 SUPER ]        | |
| |  GPU Temp             36 °C                             | |
| |  VRAM Resident        1.5 / 8 GB                        | |
| |  [==== 19% ===========================================] | |
| |  Host RAM             7.5 / 15 GB                       | |
| |  CPU Usage            29.2%                             | |
| |  CPU Temp             48 °C                             | |
| +---------------------------------------------------------+ |
+-------------------------------------------------------------+
```

---

## 2. Architectural Boundaries & Data Flow

```mermaid
flowchart TD
    subgraph Host OS Layer
        SMI["nvidia-smi / ROCm / sysctl"]
        PSUTIL["psutil.virtual_memory() & cpu_percent()"]
        PROCMEM["/proc/meminfo Fallback"]
    end

    subgraph Python Backend Bridge
        TB["TelemetryBridge.get_system_telemetry()"]
        SMI --> TB
        PSUTIL --> TB
        PROCMEM --> TB
        FACADE["DesktopBridgeAPI (PyWebView js_api)"]
        TB --> FACADE
    end

    subgraph Frontend Runtime (Vanilla ES6)
        NB["NativeBridge.getSystemTelemetry()"]
        FACADE -->|"pywebview.api RPC"| NB
        MGR["DeskAITelemetry Lifecycle Manager\n(sync & startPolling)"]
        NB --> MGR
        STORE["StudioStore (state.telemetry)"]
        MGR -->|"Mutates"| STORE
        VIEW["Hardware Dock DOM (#hardwareDock)"]
        STORE -->|"Subscribes"| VIEW
    end
```

### Key Architectural Tenets
1. **Truthful Telemetry Only:** Never fabricate or hardcode device specs. When hardware is absent, probing fails, or metrics are uninitialized, render the neutral `--color-unknown: #8a8e97` token and explicit "Unavailable" status with descriptive tooltip.
2. **In-Flow Layout Geometry:** Anchored via `position: relative; flex-shrink: 0;` inside `.sidebar-left` (`flex-direction: column`). The File Explorer Tree above occupies `flex: 1 1 0%; min-height: 0;`, guaranteeing zero file occlusion.
3. **Throttled Probing & Battery Preservation:** Subprocess queries are cached with a 3-second TTL. Background polling is throttled to 5000ms and pauses automatically when `document.hidden` is true.

---

## 3. Sub-Component Breakdown

| Sub-Component | DOM ID / Class | Architectural Responsibility |
| :--- | :--- | :--- |
| **Dock Container** | `#hardwareDock` / `.hardware-dock` | Section landmark (`role="region"`, `aria-label="Host System Telemetry"`) pinned below explorer. |
| **GPU Status Badge** | `#teleGpuBadge` / `.gpu-badge` | Live region (`aria-live="polite"`) displaying `.status-dot.ready` or `.status-dot.unknown` and GPU model. |
| **GPU Temp Indicator** | `#teleGpuTempText` / `.tele-val` | Real-time GPU core temperature with dynamic thermal color classes (`.temp-cool`, `.temp-warm`, `.temp-hot`). |
| **VRAM Usage Meter** | `#teleVramText`, `#teleVramTrack`, `#teleVramFill` | Textual ratio and W3C progressbar (`role="progressbar"`, `aria-label="VRAM Usage"`, `aria-valuenow`). |
| **Host RAM Indicator** | `#teleRamText` / `.ram-val` | Textual readout of host virtual memory (`${used} / ${total} GB`). |
| **CPU Usage Indicator** | `#teleCpuText` / `.tele-val` | Real-time processor utilization percentage (`xx.x%`). |
| **CPU Temp Indicator** | `#teleCpuTempText` / `.tele-val` | Live processor temperature with dynamic thermal classes matching GPU thermal thresholds. |

---

## 4. Accessibility & Responsive Specifications

- **Landmark Hierarchy:** Rendered as `<footer class="hardware-dock" role="region" aria-label="Host System Telemetry">` to avoid invalid nested `role="contentinfo"` within `<aside>`.
- **Contrast & Tokenization:** Uses semantic design tokens from `tokens.css`:
  - Ready state: `--color-success: #22c55e` (contrast > 4.5:1 against dark header background).
  - Unknown/idle state: `--color-unknown: #8a8e97` and `--color-unknown-subtle: rgba(138, 142, 151, 0.15)`.
- **Sidebar Collapse Integration:** When the Left Sidebar is collapsed (`#sidebarLeft.collapsed`), the dock collapses cleanly with the sidebar (`width: 0; overflow: hidden;`).
