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
  }
};
