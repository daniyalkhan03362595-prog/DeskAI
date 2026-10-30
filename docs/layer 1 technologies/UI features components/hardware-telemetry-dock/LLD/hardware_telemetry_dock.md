# Low-Level Design (LLD): Hardware Telemetry Dock

**Component Path:** `docs/layer 1 technologies/UI features components/hardware-telemetry-dock/`  
**DOM Target:** `#hardwareDock` inside `<aside class="sidebar-left" id="sidebarLeft">`  
**Files:**
- Markup: `src/deskai/static/index.html`
- Styles: `src/deskai/static/css/components.css`, `src/deskai/static/css/tokens.css`
- Frontend Scripts: `src/deskai/static/js/bridge.js`, `src/deskai/static/js/app.js`, `src/deskai/static/js/state.js`
- Backend Bridge: `src/deskai/bridge/telemetry.py`, `src/deskai/bridge/api.py`

---

## 1. DOM Markup Specification

```html
<!-- Hardware Status Dock -->
<footer class="hardware-dock" id="hardwareDock" role="region" aria-label="Host System Telemetry">
  <div class="telemetry-row">
    <span class="tele-label">GPU Acceleration</span>
    <span class="tele-badge gpu-badge unknown" id="teleGpuBadge" title="Hardware telemetry unavailable on this host" aria-live="polite">
      <span class="status-dot unknown"></span> Unavailable
    </span>
  </div>
  <div class="telemetry-row">
    <span class="tele-label">GPU Temp</span>
    <span class="tele-val unknown" id="teleGpuTempText" title="GPU temperature unavailable" aria-live="polite">—</span>
  </div>
  <div class="telemetry-row">
    <span class="tele-label">VRAM Resident</span>
    <span class="tele-val unknown" id="teleVramText" title="Hardware telemetry unavailable on this host">Unavailable</span>
  </div>
  <div class="vram-meter-track unknown" id="teleVramTrack" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="VRAM Usage">
    <div class="vram-meter-fill unknown" id="teleVramFill"></div>
  </div>
  <div class="telemetry-row">
    <span class="tele-label">Host RAM</span>
    <span class="tele-val ram-val unknown" id="teleRamText" title="Hardware telemetry unavailable on this host">Unavailable</span>
  </div>
  <div class="telemetry-row">
    <span class="tele-label">CPU Usage</span>
    <span class="tele-val unknown" id="teleCpuText" title="CPU usage unavailable" aria-live="polite">—</span>
  </div>
  <div class="telemetry-row">
    <span class="tele-label">CPU Temp</span>
    <span class="tele-val unknown" id="teleCpuTempText" title="CPU temperature unavailable" aria-live="polite">—</span>
  </div>
</footer>
```

---

## 2. CSS Layout Geometry (`components.css`)

```css
/* Sidebar Flexbox Container: in-flow layout prevents file tree occlusion */
.sidebar-left {
  background-color: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.explorer-container {
  flex: 1 1 0%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Hardware Status Dock */
.hardware-dock {
  flex-shrink: 0;
  position: relative;
  background-color: var(--bg-header);
  border-top: 1px solid var(--border-subtle);
  padding: var(--space-3);
  z-index: var(--z-sticky-footer);
  font-size: var(--text-xs);
}

.telemetry-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.tele-label {
  color: var(--text-muted);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  vertical-align: middle;
  margin-right: 4px;
}

.status-dot.ready {
  background-color: var(--color-success);
}

.status-dot.unknown {
  background-color: var(--color-unknown);
}

.tele-badge {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: 10px;
  background-color: var(--bg-surface);
  display: inline-flex;
  align-items: center;
}

.tele-badge.unknown {
  color: var(--color-unknown);
  background-color: var(--color-unknown-subtle);
  border: 1px solid var(--border-subtle);
}

.tele-val.unknown {
  color: var(--color-unknown);
  font-style: italic;
}

.vram-meter-track {
  width: 100%;
  height: 5px;
  background-color: var(--border-subtle);
  border-radius: 3px;
  overflow: hidden;
  margin: var(--space-1) 0 var(--space-2) 0;
}

.vram-meter-track.unknown {
  opacity: 0.35;
}

.vram-meter-fill {
  height: 100%;
  width: 40%;
  background: linear-gradient(to right, var(--color-primary-hover), var(--color-amber));
  border-radius: 3px;
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.vram-meter-fill.unknown {
  background: var(--color-unknown);
  width: 0% !important;
}

/* Temperature colour states (GPU & CPU) */
.tele-val.temp-cool { color: var(--color-success); }
.tele-val.temp-warm { color: var(--color-amber); }
.tele-val.temp-hot  { color: var(--color-danger); font-weight: 600; }
```

---

## 3. Backend Implementation Specification (`telemetry.py`)

### Data Contract (`get_system_telemetry`)
```json
{
  "status": "ok",
  "telemetry": {
    "gpuName": "NVIDIA GeForce RTX 2070 SUPER",
    "vramUsedMB": 1459,
    "vramTotalMB": 8192,
    "gpuTempC": 34,
    "cpuTempC": 48,
    "cpuUsagePct": "2.4%",
    "ramUsedMB": 7703,
    "ramTotalMB": 15417,
    "status": "ready",
    "platform": "Linux"
  }
}
```

> **Fallback values:** `"--"` for string fields, `"unavailable"` for `cpuUsagePct` when psutil is absent.

### Probing Strategy:
1. **NVIDIA Devices:** Probes `nvidia-smi` with `--query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits` (timeout 1.5s). Returns integer `gpuTempC` when available.
2. **Apple Silicon:** Probes Darwin `sysctl -n machdep.cpu.brand_string` with unified host memory mapping. `gpuTempC` returns `"--"` (SMC not accessible in userspace).
3. **AMD Linux:** Reads `/sys/class/drm/card*/device/mem_info_vram_total`, `mem_info_vram_used`, and hwmon temperature via `/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input` (millidegrees ÷ 1000).
4. **CPU Thermal Probing:** Evaluates `psutil.sensors_temperatures()` looking for `coretemp` (Package id 0), `k10temp`, `zenpower`, or `cpu_thermal`. Falls back to `/sys/class/thermal/thermal_zone*/temp` on Linux sysfs. Returns integer degrees or `"--"`.
5. **Caching:** GPU probe results are memoized in memory for 3.0 seconds to prevent subprocess execution thrashing; CPU thermal and usage reads are in-memory kernel sysfs reads (<0.1ms).
6. **Origin Verification:** Enforced via `_is_origin_allowed()`.

---

## 4. Frontend Implementation Specification

### 4.1 NativeBridge RPC Method (`bridge.js`)
```javascript
async getSystemTelemetry() {
  await this.whenReady();
  if (
    window.pywebview &&
    window.pywebview.api &&
    typeof window.pywebview.api.get_system_telemetry === "function"
  ) {
    return await window.pywebview.api.get_system_telemetry();
  }
  return { status: "error", message: "Bridge unavailable", telemetry: null };
}
```

### 4.2 Lifecycle Manager & Polling (`app.js`)
```javascript
export const DeskAITelemetry = {
  timer: null,
  async sync() {
    if (
      window.pywebview &&
      window.pywebview.api &&
      typeof window.pywebview.api.get_system_telemetry === "function"
    ) {
      try {
        const res = await NativeBridge.getSystemTelemetry();
        if (res && res.status === "ok" && res.telemetry) {
          store.state.telemetry = res.telemetry;
          return res.telemetry;
        }
      } catch (err) {
        console.warn("[Telemetry] Sync error:", err);
      }
    }
    return null;
  },
  startPolling(intervalMs = 5000) {
    this.stopPolling();
    if (!window.pywebview || !window.pywebview.api) return;
    this.sync();
    this.timer = setInterval(() => {
      if (!document.hidden) {
        this.sync();
      }
    }, intervalMs);
  },
  stopPolling() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
};
```

---

## 5. Automated Verification Plan

| Test File | Test Case | Target Assertion |
| :--- | :--- | :--- |
| `tests/test_hardware_telemetry_dock.py` | `test_backend_detect_host_gpu_structure` | `gpuName`, `vramUsedMB`, `vramTotalMB` populated |
| `tests/test_hardware_telemetry_dock.py` | `test_hardware_dock_layout_not_absolute` | `#hardwareDock` is `position: relative`, `.sidebar-left` is `column` |
| `tests/test_hardware_telemetry_dock.py` | `test_hardware_dock_accessibility_attributes` | `role="region"`, `aria-label="Host System Telemetry"`, `aria-label="VRAM Usage"` |
| `tests/test_hardware_telemetry_dock.py` | `test_frontend_bridge_has_get_system_telemetry_method` | `typeof window.NativeBridge.getSystemTelemetry === 'function'` |
| `tests/test_hardware_telemetry_dock.py` | `test_deskai_telemetry_sync_updates_dom_truthfully` | DOM elements update with real metrics without emojis |
| `tests/test_task5_telemetry_and_terminal_controls.py` | `test_telemetry_initial_state_shows_unavailable_and_no_ready` | Standalone browser initially renders "Unavailable" with neutral tokens |
