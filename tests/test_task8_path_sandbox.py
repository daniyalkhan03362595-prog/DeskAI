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
        if os.name != "nt":
            self.assertTrue(is_disallowed_workspace_root("/bin"))
            self.assertTrue(is_disallowed_workspace_root("/sbin"))
            self.assertTrue(is_disallowed_workspace_root("/opt"))
            self.assertTrue(is_disallowed_workspace_root("/srv"))
            self.assertTrue(is_disallowed_workspace_root("/snap"))
            self.assertTrue(is_disallowed_workspace_root("/lib"))
            self.assertTrue(is_disallowed_workspace_root("/lib64"))
        else:
            self.assertTrue(is_disallowed_workspace_root("C:\\Windows"))
            self.assertTrue(is_disallowed_workspace_root("C:\\Program Files"))
            self.assertTrue(is_disallowed_workspace_root("C:\\ProgramData"))

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

    def test_select_folder_rejects_disallowed_system_root(self):
        """select_folder must reject picking disallowed system directories like /etc or /bin."""
        disallowed = "C:\\Windows" if os.name == "nt" else "/etc"
        self.mock_window.create_file_dialog.return_value = [disallowed]
        res = self.api.select_folder()
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Disallowed system directory", res.get("message", ""))

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
            with patch.object(os.path, "getsize", return_value=11 * 1024 * 1024):
                res_large = self.api.read_file(inside_file)
                self.assertEqual(res_large.get("status"), "error")
                self.assertIn("10MB", res_large.get("message", ""))

    def test_ancestor_root_sensitive_dirs_and_symlinks_denied(self):
        """Ancestor root + ~/.ssh read/list/write/delete/create/rename all denied; symlink to ~/.ssh denied."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_home = os.path.realpath(os.path.join(temp_dir, "home", "alice"))
            ssh_dir = os.path.join(temp_home, ".ssh")
            os.makedirs(ssh_dir, exist_ok=True)
            id_rsa = os.path.join(ssh_dir, "id_rsa")
            with open(id_rsa, "w") as f:
                f.write("SUPER_SECRET_KEY")

            project_dir = os.path.join(temp_home, "my_project")
            os.makedirs(project_dir, exist_ok=True)
            ancestor_root = os.path.realpath(os.path.join(temp_dir, "home"))

            with patch.dict(os.environ, {"HOME": temp_home}):
                self.api.workspace_root = ancestor_root

                # 1. read_file in ~/.ssh -> denied
                res_read = self.api.read_file(id_rsa)
                self.assertEqual(res_read["status"], "error")
                self.assertIn("Access denied", res_read["message"])

                # 2. write_file in ~/.ssh -> denied
                res_write = self.api.write_file(os.path.join(ssh_dir, "pwned.txt"), "bad")
                self.assertEqual(res_write["status"], "error")
                self.assertIn("Access denied", res_write["message"])

                # 3. list_dir on ~/.ssh -> denied
                res_list = self.api.list_dir(ssh_dir)
                self.assertEqual(res_list["status"], "error")
                self.assertIn("Access denied", res_list["message"])

                # 4. create_dir in ~/.ssh -> denied
                res_mkdir = self.api.create_dir(os.path.join(ssh_dir, "subfolder"))
                self.assertEqual(res_mkdir["status"], "error")
                self.assertIn("Access denied", res_mkdir["message"])

                # 5. rename_path in ~/.ssh -> denied
                res_rename = self.api.rename_path(id_rsa, os.path.join(ssh_dir, "id_rsa_bak"))
                self.assertEqual(res_rename["status"], "error")
                self.assertIn("Access denied", res_rename["message"])

                # 6. delete_path in ~/.ssh -> denied
                res_del = self.api.delete_path(id_rsa)
                self.assertEqual(res_del["status"], "error")
                self.assertIn("Access denied", res_del["message"])

                # 7. Symlink inside normal workspace pointing to ~/.ssh is denied
                self.api.workspace_root = project_dir
                symlink_target = os.path.join(project_dir, "ssh_symlink")
                try:
                    os.symlink(ssh_dir, symlink_target)
                    self.assertFalse(is_safe_workspace_path(symlink_target, project_dir))
                    self.assertFalse(is_safe_workspace_path(os.path.join(symlink_target, "id_rsa"), project_dir))

                    res_sym_read = self.api.read_file(os.path.join(symlink_target, "id_rsa"))
                    self.assertEqual(res_sym_read["status"], "error")
                    self.assertIn("Access denied", res_sym_read["message"])

                    # list_dir on project_dir does not expose symlink pointing to sensitive dir
                    res_proj_list = self.api.list_dir()
                    self.assertEqual(res_proj_list["status"], "ok")
                    names = [e["name"] for e in res_proj_list.get("entries", [])]
                    self.assertNotIn("ssh_symlink", names)
                except OSError:
                    pass

    def test_windows_realpath_and_sensitive_checks_mocked(self):
        """Mocked Windows branch tests realpath and system/sensitive dir rejection."""
        with patch("deskai.utils.path.os.name", "nt"), patch("sys.platform", "win32"):
            with patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\alice"}):
                # Ancestor C:\Users containing C:\Users\alice\.ssh\id_rsa
                self.assertFalse(is_safe_workspace_path("C:\\Users\\alice\\.ssh\\id_rsa", "C:\\Users"))
                self.assertFalse(is_safe_workspace_path("C:\\Windows\\System32\\cmd.exe", "C:\\"))
                self.assertFalse(is_safe_workspace_path("C:\\Program Files\\App\\app.exe", "C:\\"))
                # Normal file in user project is safe
                self.assertTrue(
                    is_safe_workspace_path(
                        "C:\\Users\\alice\\projects\\deskai\\main.py", "C:\\Users\\alice\\projects\\deskai"
                    )
                )

    def test_macos_private_prefixes_and_case_insensitivity_mocked(self):
        """Mocked macOS branch verifies /private/etc, /private/var, /private/tmp and case insensitivity."""
        with patch("sys.platform", "darwin"):
            self.assertFalse(is_safe_workspace_path("/private/etc/hosts", "/private"))
            self.assertFalse(is_safe_workspace_path("/PRIVATE/ETC/HOSTS", "/private"))
            self.assertFalse(is_safe_workspace_path("/private/var/log/syslog", "/private"))
            self.assertFalse(is_safe_workspace_path("/private/tmp/secret.txt", "/private"))
            self.assertTrue(is_disallowed_workspace_root("/private/etc"))
            self.assertTrue(is_disallowed_workspace_root("/PRIVATE/ETC"))
            self.assertTrue(is_disallowed_workspace_root("/private/var"))
            self.assertTrue(is_disallowed_workspace_root("/private/tmp"))


if __name__ == "__main__":
    unittest.main()
