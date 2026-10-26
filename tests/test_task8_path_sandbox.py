import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from deskai.utils.path import is_disallowed_workspace_root, is_safe_workspace_path
from deskai.bridge.api import DesktopBridgeAPI


class TestPathSandboxAndFileOperations(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"

        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_disallowed_system_prefixes_and_home_root(self):
        """Disallowed roots must reject system bins, opt, srv, sensitive dirs, and home root itself."""
        # Linux system prefixes
        self.assertTrue(is_disallowed_workspace_root("/bin"))
        self.assertTrue(is_disallowed_workspace_root("/sbin"))
        self.assertTrue(is_disallowed_workspace_root("/opt"))
        self.assertTrue(is_disallowed_workspace_root("/srv"))
        self.assertTrue(is_disallowed_workspace_root("/snap"))
        self.assertTrue(is_disallowed_workspace_root("/lib"))
        self.assertTrue(is_disallowed_workspace_root("/lib64"))

        # User home root must be disallowed
        home = os.path.realpath(os.path.expanduser("~"))
        self.assertTrue(is_disallowed_workspace_root(home))

        # Sensitive user directories inside home
        self.assertTrue(is_disallowed_workspace_root(os.path.expanduser("~/.ssh")))
        self.assertTrue(is_disallowed_workspace_root(os.path.expanduser("~/.aws")))
        self.assertTrue(is_disallowed_workspace_root(os.path.expanduser("~/.gnupg")))

        # But a subfolder inside home should be allowed
        sub_project = os.path.join(home, "my_safe_project_dir")
        self.assertFalse(is_disallowed_workspace_root(sub_project))

    def test_workspace_path_sandbox_guards(self):
        """Test symlink escapes, parent traversal, sibling prefix attack."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ws_root = os.path.join(temp_dir, "workspace")
            os.makedirs(ws_root)
            secret_sibling = os.path.join(temp_dir, "workspace-secrets")
            os.makedirs(secret_sibling)
            outside_target = os.path.join(temp_dir, "outside.txt")
            with open(outside_target, "w") as f:
                f.write("secret data")

            # 1. Normal safe file in workspace
            safe_file = os.path.join(ws_root, "app.py")
            self.assertTrue(is_safe_workspace_path(safe_file, ws_root))

            # 2. Parent directory traversal ../
            traversal_file = os.path.join(ws_root, "../outside.txt")
            self.assertFalse(is_safe_workspace_path(traversal_file, ws_root))

            # 3. Sibling prefix attack (/workspace vs /workspace-secrets)
            sibling_file = os.path.join(secret_sibling, "passwords.txt")
            self.assertFalse(is_safe_workspace_path(sibling_file, ws_root))

            # 4. Symlink escape
            symlink_file = os.path.join(ws_root, "sym_escape.txt")
            try:
                os.symlink(outside_target, symlink_file)
                self.assertFalse(is_safe_workspace_path(symlink_file, ws_root))
            except OSError:
                pass

    @patch("deskai.utils.path.os.name", "nt")
    def test_windows_case_insensitive_disallowed_roots(self):
        """On Windows, lower/upper case roots like c:\\windows must be disallowed."""
        self.assertTrue(is_disallowed_workspace_root("c:\\windows"))
        self.assertTrue(is_disallowed_workspace_root("C:\\WINDOWS\\system32"))
        self.assertTrue(is_disallowed_workspace_root("c:\\program files"))
        self.assertTrue(is_disallowed_workspace_root("C:\\PROGRAMDATA"))
        self.assertTrue(is_disallowed_workspace_root("D:\\"))

    def test_bridge_read_write_list_operations(self):
        """Test read_file, write_file, and list_dir in sandbox."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ws_root = os.path.realpath(os.path.join(temp_dir, "my_project"))
            os.makedirs(ws_root)
            self.api.workspace_root = ws_root

            outside_file = os.path.realpath(os.path.join(temp_dir, "outside.txt"))
            with open(outside_file, "w") as f:
                f.write("secret")

            # 1. Write file inside workspace
            inside_file = os.path.join(ws_root, "hello.txt")
            res_write = self.api.write_file(inside_file, "Hello DeskAI!")
            self.assertEqual(res_write.get("status"), "ok")

            # 2. Read file inside workspace
            res_read = self.api.read_file(inside_file)
            self.assertEqual(res_read.get("status"), "ok")
            self.assertEqual(res_read.get("content"), "Hello DeskAI!")

            # 3. Read outside file -> denied
            res_outside = self.api.read_file(outside_file)
            self.assertEqual(res_outside.get("status"), "error")

            # 4. Write outside file -> denied
            res_write_out = self.api.write_file(outside_file, "hacked")
            self.assertEqual(res_write_out.get("status"), "error")

            # 5. List dir inside workspace (should list hello.txt, skip .hidden)
            hidden_file = os.path.join(ws_root, ".git")
            with open(hidden_file, "w") as f:
                f.write("git file")

            res_list = self.api.list_dir()
            self.assertEqual(res_list.get("status"), "ok")
            entry_names = [e["name"] for e in res_list.get("entries", [])]
            self.assertIn("hello.txt", entry_names)
            self.assertNotIn(".git", entry_names)

            # 6. File exceeding 10MB rejected
            large_file = os.path.join(ws_root, "large.bin")
            with patch("os.path.getsize", return_value=11 * 1024 * 1024):
                res_large = self.api.read_file(inside_file)
                self.assertEqual(res_large.get("status"), "error")
                self.assertIn("10MB", res_large.get("message", ""))


if __name__ == "__main__":
    unittest.main()
