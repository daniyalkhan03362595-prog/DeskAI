/**
 * DiagnosticsStore: Manages workspace diagnostics with replace-set semantics.
 * High-performance plain store outside deep reactive proxy to scale to thousands of items.
 */

export class DiagnosticsStore {
  constructor() {
    this._bySourceFile = new Map();
    this._listeners = new Set();
    this._version = 0;
  }

  static key(path) {
    if (!path) return "";
    const p = String(path).replace(/\\/g, "/");
    const isWin = typeof navigator !== "undefined" && navigator.platform && navigator.platform.startsWith("Win");
    return isWin ? p.toLowerCase() : p;
  }

  replace(source, file, items) {
    const k = `${source}\u0000${DiagnosticsStore.key(file)}`;
    if (!items || items.length === 0) {
      if (this._bySourceFile.has(k)) {
        this._bySourceFile.delete(k);
        this._emit();
      }
    } else {
      this._bySourceFile.set(k, { source, file, items });
      this._emit();
    }
  }

  clearFile(file) {
    const fileKey = DiagnosticsStore.key(file);
    let changed = false;
    for (const [k, v] of this._bySourceFile.entries()) {
      if (DiagnosticsStore.key(v.file) === fileKey) {
        this._bySourceFile.delete(k);
        changed = true;
      }
    }
    if (changed) {
      this._emit();
    }
  }

  clearAll() {
    if (this._bySourceFile.size > 0) {
      this._bySourceFile.clear();
      this._emit();
    }
  }

  counts() {
    let errors = 0;
    let warnings = 0;
    let infos = 0;
    for (const entry of this._bySourceFile.values()) {
      for (const d of entry.items) {
        if (d.severity === "error") errors++;
        else if (d.severity === "warning") warnings++;
        else if (d.severity === "info") infos++;
      }
    }
    return { errors, warnings, infos };
  }

  grouped(filter = null) {
    const fileMap = new Map();
    for (const entry of this._bySourceFile.values()) {
      for (const d of entry.items) {
        if (filter) {
          if (filter.severities && !filter.severities.has(d.severity)) continue;
          if (filter.query) {
            const q = filter.query.toLowerCase();
            const msg = (d.message || "").toLowerCase();
            const fl = (d.file || "").toLowerCase();
            const src = (d.source || "").toLowerCase();
            const cd = (d.code || "").toLowerCase();
            if (!msg.includes(q) && !fl.includes(q) && !src.includes(q) && !cd.includes(q)) {
              continue;
            }
          }
        }
        if (!fileMap.has(d.file)) {
          fileMap.set(d.file, []);
        }
        fileMap.get(d.file).push(d);
      }
    }

    const sortedMap = new Map();
    const sortedFiles = Array.from(fileMap.keys()).sort((a, b) => a.localeCompare(b));
    for (const file of sortedFiles) {
      const items = fileMap.get(file);
      items.sort((a, b) => {
        const lineA = a.range ? a.range.startLine : a.start_line || 1;
        const lineB = b.range ? b.range.startLine : b.start_line || 1;
        if (lineA !== lineB) return lineA - lineB;
        const colA = a.range ? a.range.startCol : a.start_col || 1;
        const colB = b.range ? b.range.startCol : b.start_col || 1;
        if (colA !== colB) return colA - colB;
        return (a.source || "").localeCompare(b.source || "");
      });
      sortedMap.set(file, items);
    }
    return sortedMap;
  }

  signature() {
    return this._version;
  }

  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _emit() {
    this._version++;
    this._listeners.forEach((fn) => {
      try {
        fn();
      } catch (e) {
        console.error("[DiagnosticsStore] subscriber error:", e);
      }
    });
  }
}
