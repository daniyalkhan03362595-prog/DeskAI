"""
Workspace Filesystem Bridge Module.
Handles sandboxed file reads, atomic writes, directories, renaming, deletion, and file/folder dialogs.
"""

import logging
import os
import shutil
import tempfile
import webview

from deskai.bridge.base import BaseBridgeModule
from deskai.utils.path import is_safe_workspace_path, canonicalize_path, is_disallowed_workspace_root

logger = logging.getLogger(__name__)


# Support both pywebview 6.x (webview.FileDialog) and 5.x (webview.FOLDER_DIALOG)
def _get_dialog_type(name: str, fallback_attr: str, default_code: int):
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog and hasattr(file_dialog, name):
        return getattr(file_dialog, name)
    return getattr(webview, fallback_attr, default_code)


DIALOG_FOLDER = _get_dialog_type("FOLDER", "FOLDER_DIALOG", 20)
DIALOG_OPEN = _get_dialog_type("OPEN", "OPEN_DIALOG", 10)
DIALOG_SAVE = _get_dialog_type("SAVE", "SAVE_DIALOG", 30)


class WorkspaceFSBridge(BaseBridgeModule):
    """Bridge methods for sandboxed workspace file system operations."""

    def _is_safe_path(self, target_path: str) -> bool:
        """Internal sandbox helper."""
        return is_safe_workspace_path(target_path, self.workspace_root)

    def select_folder(self) -> dict:
        """Opens native OS folder selection dialog."""
        if not self._is_origin_allowed() or self._window is None:
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_FOLDER)
        if selected and len(selected) > 0:
            target = selected[0] if isinstance(selected, (list, tuple)) else selected
            folder_path = canonicalize_path(str(target))
            if is_disallowed_workspace_root(folder_path) or not is_safe_workspace_path(folder_path, folder_path):
                return {"status": "error", "message": "Disallowed system directory", "path": None}
            self.workspace_root = folder_path
            return {"status": "ok", "path": folder_path, "name": os.path.basename(folder_path)}
        return {"status": "cancelled", "path": None}

    def set_workspace_root(self, root_path: str) -> dict:
        """Sets and validates the active workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        if not root_path:
            return {"status": "error", "message": "Invalid root path", "path": None}
        canonical = canonicalize_path(root_path)
        if not os.path.isdir(canonical):
            return {"status": "error", "message": "Directory not found", "path": None}
        if is_disallowed_workspace_root(canonical):
            return {"status": "error", "message": "Disallowed workspace root", "path": None}
        if not is_safe_workspace_path(canonical, canonical):
            return {"status": "error", "message": "Unsafe workspace root", "path": None}
        self.workspace_root = canonical
        return {"status": "ok", "path": canonical, "name": os.path.basename(canonical)}

    def get_workspace_root(self) -> dict:
        """Returns the current active workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        return {
            "status": "ok",
            "path": self.workspace_root,
            "name": os.path.basename(self.workspace_root) if self.workspace_root else None,
        }

    def select_file(self) -> dict:
        """Opens native OS file selection dialog."""
        if not self._is_origin_allowed() or self._window is None:
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_OPEN)
        if selected and len(selected) > 0:
            target = selected[0] if isinstance(selected, (list, tuple)) else selected
            file_path = canonicalize_path(str(target))
            if self.workspace_root:
                if not self._is_safe_path(file_path):
                    return {"status": "error", "message": "Access denied: Path outside workspace", "path": None}
            else:
                parent_dir = os.path.dirname(file_path)
                if is_disallowed_workspace_root(parent_dir) or not is_safe_workspace_path(parent_dir, parent_dir):
                    return {"status": "error", "message": "Disallowed workspace root", "path": None}
                if not is_safe_workspace_path(file_path, parent_dir):
                    return {"status": "error", "message": "Access denied: Path outside workspace", "path": None}
                self.workspace_root = parent_dir
            return {
                "status": "ok",
                "path": file_path,
                "name": os.path.basename(file_path),
                "workspace_root": self.workspace_root,
            }
        return {"status": "cancelled", "path": None}

    def save_file_dialog(self, default_name: str = "untitled.txt") -> dict:
        """Opens native OS file save dialog."""
        if not self._is_origin_allowed() or self._window is None:
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_SAVE, save_filename=default_name)
        if selected:
            target = selected[0] if isinstance(selected, (list, tuple)) else selected
            if not target:
                return {"status": "cancelled", "path": None}
            canonical = canonicalize_path(str(target))
            if self.workspace_root:
                if not self._is_safe_path(canonical):
                    return {"status": "error", "message": "Access denied: Path outside workspace", "path": None}
            else:
                parent_dir = os.path.dirname(canonical)
                if is_disallowed_workspace_root(parent_dir) or not is_safe_workspace_path(parent_dir, parent_dir):
                    return {"status": "error", "message": "Disallowed workspace root", "path": None}
            return {"status": "ok", "path": canonical}
        return {"status": "cancelled", "path": None}

    def read_file(self, target_path: str) -> dict:
        """Reads sandboxed file within workspace root. Max 10MB."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "content": None}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace", "content": None}

        canonical = canonicalize_path(target_path)
        if not os.path.isfile(canonical):
            return {"status": "error", "message": "File not found", "content": None}

        if os.path.getsize(canonical) > 10 * 1024 * 1024:
            return {"status": "error", "message": "File exceeds maximum 10MB size limit", "content": None}

        try:
            with open(canonical, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "ok", "content": content, "path": canonical}
        except UnicodeDecodeError:
            return {"status": "error", "message": "File is not valid UTF-8 text", "content": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "content": None}

    def write_file(self, target_path: str, content: str) -> dict:
        """Atomically writes file within workspace root preserving permissions and cleaning temp files."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace"}

        canonical = canonicalize_path(target_path)
        parent_dir = os.path.dirname(canonical)
        os.makedirs(parent_dir, exist_ok=True)

        temp_name = None
        target_existed = os.path.exists(canonical)
        try:
            with tempfile.NamedTemporaryFile("w", dir=parent_dir, encoding="utf-8", delete=False) as tf:
                temp_name = tf.name
                tf.write(content)
                tf.flush()
                os.fsync(tf.fileno())

            if target_existed:
                try:
                    shutil.copymode(canonical, temp_name)
                except OSError:
                    pass
            else:
                try:
                    current_umask = os.umask(0)
                    os.umask(current_umask)
                    new_mode = 0o666 & ~current_umask
                    os.chmod(temp_name, new_mode)
                except (OSError, AttributeError):
                    pass

            os.replace(temp_name, canonical)
            temp_name = None
            return {"status": "ok", "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except OSError:
                    pass

    def create_dir(self, target_path: str) -> dict:
        """Safely creates a directory within workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace"}

        canonical = canonicalize_path(target_path)
        try:
            os.makedirs(canonical, exist_ok=True)
            return {"status": "ok", "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def rename_path(self, old_path: str, new_path: str, overwrite: bool = False) -> dict:
        """Safely renames a file or directory inside workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if not self._is_safe_path(old_path) or not self._is_safe_path(new_path):
            return {"status": "error", "message": "Access denied: Path outside workspace"}

        old_canonical = canonicalize_path(old_path)
        new_canonical = canonicalize_path(new_path)

        if not os.path.exists(old_canonical):
            return {"status": "error", "message": "Source path does not exist", "code": "ENOENT"}

        if os.path.exists(new_canonical) and not overwrite:
            return {
                "status": "error",
                "code": "EEXIST",
                "message": f"Destination already exists: {os.path.basename(new_canonical)}",
            }

        try:
            os.replace(old_canonical, new_canonical)
            return {"status": "ok", "old_path": old_canonical, "new_path": new_canonical}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_path(self, target_path: str) -> dict:
        """Safely deletes a file or directory within workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace"}

        canonical = canonicalize_path(target_path)
        if self.workspace_root and canonical == canonicalize_path(self.workspace_root):
            return {"status": "error", "message": "Cannot delete workspace root"}

        if not os.path.exists(canonical):
            return {"status": "error", "message": "Path not found"}

        try:
            if os.path.isdir(canonical):
                shutil.rmtree(canonical)
            else:
                os.remove(canonical)
            return {"status": "ok", "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_dir(self, target_path: str | None = None) -> dict:
        """Lists directory entries safely inside workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "entries": []}

        path_to_list = target_path if target_path else self.workspace_root
        if not path_to_list or not self._is_safe_path(path_to_list):
            return {"status": "error", "message": "Access denied: Path outside workspace", "entries": []}

        canonical = canonicalize_path(path_to_list)
        if not os.path.isdir(canonical):
            return {"status": "error", "message": "Directory not found", "entries": []}

        try:
            entries = []
            with os.scandir(canonical) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    if not self._is_safe_path(entry.path):
                        continue
                    entries.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "path": canonicalize_path(entry.path),
                        }
                    )
            entries.sort(key=lambda x: (not x["is_dir"], str(x["name"]).lower()))
            return {"status": "ok", "entries": entries, "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e), "entries": []}
