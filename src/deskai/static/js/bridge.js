/**
 * NativeBridge RPC Wrapper
 * Interfaces safely with window.pywebview.api
 */
export const NativeBridge = {
  async selectFolder() {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.select_folder();
    }
    console.warn("[Bridge] pywebview.api not ready.");
    return { status: "cancelled", path: null };
  },

  async selectFile() {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.select_file();
    }
    return { status: "cancelled", path: null };
  },

  async saveFileDialog(filename = "untitled.txt") {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.save_file_dialog(filename);
    }
    return { status: "cancelled", path: null };
  },

  async windowControl(action, direction = null, timestamp = null) {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.window_control(action, direction, timestamp);
    }
    return false;
  },

  async dragWindow(timestamp = null) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.drag_window) {
      return await window.pywebview.api.drag_window(timestamp);
    }
    return false;
  },

  async resizeWindow(edge, timestamp = null) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.resize_window) {
      return await window.pywebview.api.resize_window(edge, timestamp);
    }
    return false;
  },

  async resizeWindowAbsolute(width, height) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.resize_window_absolute) {
      return await window.pywebview.api.resize_window_absolute(width, height);
    }
    return false;
  },

  async openExternalUrl(url) {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.open_external_url(url);
    }
    return false;
  },

  async terminalOpen(cols = 80, rows = 24) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.terminal_open) {
      return await window.pywebview.api.terminal_open(cols, rows);
    }
    return { status: "error", message: "Bridge not ready" };
  },

  async terminalClose(sessionId) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.terminal_close) {
      return await window.pywebview.api.terminal_close(sessionId);
    }
    return false;
  },

  async setDirtyStatus(isDirty) {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.set_dirty_status(Boolean(isDirty));
    }
    return false;
  },

  async readFile(filePath) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.read_file) {
      return await window.pywebview.api.read_file(filePath);
    }
    return { status: "error", message: "API unavailable", content: null };
  },

  async writeFile(filePath, content) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.write_file) {
      return await window.pywebview.api.write_file(filePath, content);
    }
    return { status: "error", message: "API unavailable" };
  },

  async listDir(dirPath = null) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.list_dir) {
      return await window.pywebview.api.list_dir(dirPath);
    }
    return { status: "error", message: "API unavailable", entries: [] };
  },

  whenReady() {
    if (window.pywebview && window.pywebview.api) {
      return Promise.resolve();
    }
    return new Promise(resolve => {
      let resolved = false;
      const onReady = () => {
        if (!resolved) {
          resolved = true;
          window.removeEventListener("pywebviewready", onReady);
          resolve();
        }
      };
      window.addEventListener("pywebviewready", onReady);
      setTimeout(onReady, 800);
    });
  },

  async openPort(port, host = "127.0.0.1") {
    await this.whenReady();
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_port) {
      return await window.pywebview.api.open_port(Number(port), host);
    }
    return false;
  },

  async probePort(port, host = "127.0.0.1") {
    await this.whenReady();
    if (window.pywebview && window.pywebview.api && window.pywebview.api.probe_port) {
      return await window.pywebview.api.probe_port(Number(port), host);
    }
    return false;
  },

  async listPorts() {
    await this.whenReady();
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_listening_ports) {
      return await window.pywebview.api.get_listening_ports();
    }
    // Browser fallback: detect current origin port
    const fallbackPorts = [];
    if (location.port) {
      fallbackPorts.push({
        port: parseInt(location.port, 10),
        host: location.hostname || "127.0.0.1",
        protocol: location.protocol.replace(":", "").toUpperCase(),
        address: `${location.protocol}//${location.hostname}:${location.port}`,
        process: "DeskAI Supervisor",
        pid: null,
        status: "Listening",
        origin: "System",
        exposure: "loopback",
        openable: false
      });
    }
    return { status: "ok", ports: fallbackPorts, warnings: [] };
  }
};
