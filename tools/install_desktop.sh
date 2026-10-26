#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv"

if [ -f "${VENV_DIR}/bin/deskai" ]; then
    EXEC_CMD="${VENV_DIR}/bin/deskai"
elif command -v deskai >/dev/null 2>&1; then
    EXEC_CMD="$(command -v deskai)"
else
    EXEC_CMD="${VENV_DIR}/bin/python -m deskai"
fi

ICON_SRC="${REPO_DIR}/src/deskai/static/icon.svg"
APP_DIR="${HOME}/.local/share/applications"
mkdir -p "${APP_DIR}"

DESKTOP_TARGET="${APP_DIR}/deskai.desktop"

sed -e "s|@EXEC_PATH@|${EXEC_CMD}|g" \
    -e "s|@REPO_PATH@|${REPO_DIR}|g" \
    -e "s|@ICON_PATH@|${ICON_SRC}|g" \
    "${REPO_DIR}/deskai.desktop.in" > "${DESKTOP_TARGET}"

chmod +x "${DESKTOP_TARGET}"
echo "Successfully installed ${DESKTOP_TARGET}"
