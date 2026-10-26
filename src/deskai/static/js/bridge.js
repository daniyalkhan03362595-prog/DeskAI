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

  async windowControl(action) {
    if (window.pywebview && window.pywebview.api) {
      return await window.pywebview.api.window_control(action);
    }
    return false;
  },

  async dragWindow() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.drag_window) {
      return await window.pywebview.api.drag_window();
    }
    return false;
  },

  async resizeWindow(edge) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.resize_window) {
      return await window.pywebview.api.resize_window(edge);
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
  }
};
