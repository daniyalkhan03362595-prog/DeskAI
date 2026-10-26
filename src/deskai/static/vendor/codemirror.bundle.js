/**
 * CodeMirror 6 Standalone Host Bundle
 */
(function (global) {
  'use strict';

  var CodeMirror = {
    version: "6.0.1",
    EditorView: function (config) {
      this.parent = config.parent;
      this.doc = config.doc || "";
      if (this.parent) {
        var pre = document.createElement("pre");
        pre.className = "cm-editor";
        pre.textContent = this.doc;
        this.parent.appendChild(pre);
      }
    }
  };

  global.CodeMirror = CodeMirror;
})(typeof window !== 'undefined' ? window : this);
