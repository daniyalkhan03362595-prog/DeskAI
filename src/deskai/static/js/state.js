export const initialState = {
  workspace: {
    rootPath: null,
    files: [],
    selectedPath: null
  },
  editor: {
    openTabs: [],             // Array of { id, path, name, isDirty }
    activeTabId: null
  },
  telemetry: {
    gpuName: "NVIDIA RTX 2070 Super",
    vramUsedMB: 4710,
    vramTotalMB: 8192,
    cpuUsagePct: 14.8,
    ramUsedMB: 5820,
    status: "ready"
  },
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW_DIFF | SUCCESS | FAILED | ROLLBACK | CANCELLED
    taskTitle: "",
    checklist: [],
    activeDiff: null
  },
  connection: {
    isSocketConnected: false,
    lastSeq: 0
  }
};

export class StudioStore {
  constructor(initialData) {
    this._subscribers = new Map();
    this._proxyCache = new WeakMap();
    this.state = this._createDeepProxy(initialData, "");
  }

  _createDeepProxy(target, path) {
    if (typeof target !== "object" || target === null) {
      return target;
    }

    if (this._proxyCache.has(target)) {
      return this._proxyCache.get(target);
    }

    const self = this;
    const proxyHandler = {
      get(obj, prop) {
        const val = obj[prop];
        if (typeof val === "object" && val !== null) {
          const nestedPath = path ? `${path}.${String(prop)}` : String(prop);
          return self._createDeepProxy(val, nestedPath);
        }
        return val;
      },
      set(obj, prop, value) {
        const oldValue = obj[prop];
        if (oldValue === value) return true;

        obj[prop] = value;
        const currentPath = path ? `${path}.${String(prop)}` : String(prop);
        
        self._notify(currentPath, value, oldValue);
        self._bubbleNotify(currentPath, value);
        return true;
      }
    };

    const proxy = new Proxy(target, proxyHandler);
    this._proxyCache.set(target, proxy);
    return proxy;
  }

  subscribe(path, callback) {
    if (!this._subscribers.has(path)) {
      this._subscribers.set(path, new Set());
    }
    this._subscribers.get(path).add(callback);
    return () => this._subscribers.get(path).delete(callback);
  }

  _notify(path, newValue, oldValue) {
    if (this._subscribers.has(path)) {
      for (const cb of this._subscribers.get(path)) {
        cb(newValue, oldValue);
      }
    }
  }

  _bubbleNotify(fullPath, value) {
    const parts = fullPath.split(".");
    while (parts.length > 1) {
      parts.pop();
      const parentPath = parts.join(".");
      this._notify(parentPath, value, undefined);
    }
  }
}

export const store = new StudioStore(initialState);
