#!/usr/bin/env bash
# tools/build_vendor.sh
# Builds and vendors real, pinned client-side dependencies:
# - DOMPurify (sanitizer)
# - marked (markdown parser)
# - CodeMirror 6 (editor with virtualized scrolling, syntax highlighting, dark theme)
# Generates src/deskai/static/vendor/MANIFEST.json with SHA-256 integrity hashes.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/src/deskai/static/vendor"
TMP_DIR="$(mktemp -d /tmp/deskai_vendor_build.XXXXXX)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "==> Building DeskAI Layer 1 Vendor Assets in ${TMP_DIR}..."

DOMPURIFY_VERSION="3.4.17"
MARKED_VERSION="18.1.2"
CODEMIRROR_VERSION="6.0.1"

mkdir -p "${VENDOR_DIR}"
cd "${TMP_DIR}"

echo "--> Vendoring DOMPurify ${DOMPURIFY_VERSION}..."
curl -fsSL "https://registry.npmjs.org/dompurify/-/dompurify-${DOMPURIFY_VERSION}.tgz" | tar -xz
cp package/dist/purify.min.js "${VENDOR_DIR}/purify.min.js"
rm -rf package

echo "--> Vendoring marked ${MARKED_VERSION}..."
curl -fsSL "https://registry.npmjs.org/marked/-/marked-${MARKED_VERSION}.tgz" | tar -xz
npx --yes esbuild package/lib/marked.umd.js --minify --outfile="${VENDOR_DIR}/marked.min.js"
rm -rf package

echo "--> Compiling CodeMirror 6 Bundle..."
cat << 'EOF' > package.json
{
  "name": "deskai-cm6-builder",
  "private": true
}
EOF

npm install --silent \
  @codemirror/state@6.5.2 \
  @codemirror/view@6.36.4 \
  @codemirror/language@6.10.8 \
  @codemirror/commands@6.8.0 \
  @codemirror/lang-python@6.1.7 \
  @codemirror/lang-javascript@6.2.3 \
  @codemirror/lang-markdown@6.3.2 \
  @lezer/highlight@1.2.1

cat << 'EOF' > cm_entry.js
import {
  EditorView,
  lineNumbers,
  highlightActiveLineGutter,
  highlightSpecialChars,
  drawSelection,
  dropCursor,
  highlightActiveLine,
  keymap
} from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import {
  foldGutter,
  indentOnInput,
  syntaxHighlighting,
  defaultHighlightStyle,
  bracketMatching,
  HighlightStyle
} from "@codemirror/language";
import { history, defaultKeymap, historyKeymap } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { markdown } from "@codemirror/lang-markdown";
import { tags } from "@lezer/highlight";

const deskaiTheme = EditorView.theme({
  "&": {
    color: "var(--text-primary, #ffffff)",
    backgroundColor: "transparent",
    height: "100%",
    fontSize: "var(--text-sm, 13px)",
    fontFamily: "var(--font-mono, monospace)"
  },
  ".cm-content": {
    caretColor: "var(--color-primary, #b8821d)",
    fontFamily: "var(--font-mono, monospace)"
  },
  "&.cm-focused .cm-cursor": {
    borderLeftColor: "var(--color-primary, #b8821d)"
  },
  "&.cm-focused .cm-selectionBackground, ::selection": {
    backgroundColor: "var(--color-primary-muted, rgba(184, 130, 29, 0.2))"
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    color: "var(--text-muted, #707070)",
    borderRight: "1px solid var(--border-subtle, #262626)"
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(255, 255, 255, 0.03)"
  },
  ".cm-activeLineGutter": {
    backgroundColor: "rgba(255, 255, 255, 0.05)",
    color: "var(--text-primary, #ffffff)"
  }
}, { dark: true });

const deskaiHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: "var(--color-primary, #d99a26)", fontWeight: "bold" },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName, tags.macroName], color: "var(--text-primary, #e6e6e6)" },
  { tag: [tags.function(tags.variableName), tags.labelName], color: "#e5c07b" },
  { tag: [tags.color, tags.constant(tags.name), tags.standard(tags.name)], color: "#d19a66" },
  { tag: [tags.definition(tags.name), tags.separator], color: "#e6e6e6" },
  { tag: [tags.typeName, tags.className, tags.number, tags.changed, tags.annotation, tags.modifier, tags.self, tags.namespace], color: "#e5c07b" },
  { tag: [tags.operator, tags.operatorKeyword, tags.url, tags.escape, tags.regexp, tags.link, tags.special(tags.string)], color: "#56b6c2" },
  { tag: [tags.meta, tags.comment], color: "var(--text-muted, #707070)", fontStyle: "italic" },
  { tag: tags.strong, fontWeight: "bold" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.link, color: "var(--color-primary, #b8821d)", textDecoration: "underline" },
  { tag: tags.heading, fontWeight: "bold", color: "var(--color-primary, #d99a26)" },
  { tag: [tags.atom, tags.bool, tags.special(tags.variableName)], color: "#d19a66" },
  { tag: [tags.processingInstruction, tags.string, tags.inserted], color: "#98c379" },
  { tag: tags.invalid, color: "var(--color-danger, #e74c3c)" }
]);

function createBasicExtensions(options = {}) {
  let lang = [];
  if (options.language === "python" || options.language === "py") {
    lang = python();
  } else if (options.language === "javascript" || options.language === "js" || options.language === "json") {
    lang = javascript();
  } else if (options.language === "markdown" || options.language === "md") {
    lang = markdown();
  }

  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    foldGutter(),
    drawSelection(),
    dropCursor(),
    indentOnInput(),
    syntaxHighlighting(deskaiHighlightStyle, { fallback: true }),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    bracketMatching(),
    highlightActiveLine(),
    keymap.of([...defaultKeymap, ...historyKeymap]),
    deskaiTheme,
    lang,
    ...(options.extensions || [])
  ];
}

export {
  EditorView,
  EditorState,
  lineNumbers,
  history,
  keymap,
  python,
  javascript,
  markdown,
  deskaiTheme,
  deskaiHighlightStyle,
  createBasicExtensions
};
export const version = "6.0.1";
EOF

npx --yes esbuild cm_entry.js \
  --bundle \
  --minify \
  --format=iife \
  --global-name=CodeMirror \
  '--footer:js=if (typeof window !== "undefined") window.CodeMirror = CodeMirror;' \
  --outfile="${VENDOR_DIR}/codemirror.bundle.js"

echo "--> Generating MANIFEST.json..."
PURIFY_HASH="$(sha256sum "${VENDOR_DIR}/purify.min.js" | awk '{print $1}')"
MARKED_HASH="$(sha256sum "${VENDOR_DIR}/marked.min.js" | awk '{print $1}')"
CM_HASH="$(sha256sum "${VENDOR_DIR}/codemirror.bundle.js" | awk '{print $1}')"

cat << EOF > "${VENDOR_DIR}/MANIFEST.json"
{
  "purify.min.js": {
    "name": "DOMPurify",
    "version": "${DOMPURIFY_VERSION}",
    "sha256": "${PURIFY_HASH}",
    "url": "https://registry.npmjs.org/dompurify/-/dompurify-${DOMPURIFY_VERSION}.tgz"
  },
  "marked.min.js": {
    "name": "marked",
    "version": "${MARKED_VERSION}",
    "sha256": "${MARKED_HASH}",
    "url": "https://registry.npmjs.org/marked/-/marked-${MARKED_VERSION}.tgz"
  },
  "codemirror.bundle.js": {
    "name": "CodeMirror 6 Bundle",
    "version": "${CODEMIRROR_VERSION}",
    "sha256": "${CM_HASH}",
    "url": "https://codemirror.net"
  }
}
EOF

echo "==> Vendor build complete! Hashes written to ${VENDOR_DIR}/MANIFEST.json"
