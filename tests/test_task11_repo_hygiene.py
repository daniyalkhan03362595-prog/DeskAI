import os
import unittest
from pathlib import Path


class TestRepoAndCIHygiene(unittest.TestCase):
    def test_desktop_template_and_installer(self):
        """deskai.desktop.in must contain placeholders and installer must be executable."""
        template_path = Path("deskai.desktop.in")
        self.assertTrue(template_path.exists())
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("@EXEC_PATH@", content)
        self.assertIn("@REPO_PATH@", content)
        self.assertIn("@ICON_PATH@", content)

        installer_path = Path("tools/install_desktop.sh")
        self.assertTrue(installer_path.exists())
        if os.name != "nt":
            self.assertTrue(os.access(installer_path, os.X_OK))

    def test_ci_workflow_has_windows_and_python_matrix(self):
        """CI workflow must include windows-latest, python 3.11/3.12, and black/flake8."""
        ci_path = Path(".github/workflows/ci.yml")
        self.assertTrue(ci_path.exists())
        ci_yaml = ci_path.read_text(encoding="utf-8")

        self.assertIn("windows-latest", ci_yaml)
        self.assertIn("'3.11'", ci_yaml)
        self.assertIn("'3.12'", ci_yaml)
        self.assertIn("black --check", ci_yaml)
        self.assertIn("flake8", ci_yaml)

    def test_setup_cfg_flake8_config(self):
        """setup.cfg must configure flake8 max-line-length 120."""
        cfg_path = Path("setup.cfg")
        self.assertTrue(cfg_path.exists())
        content = cfg_path.read_text(encoding="utf-8")
        self.assertIn("[flake8]", content)
        self.assertIn("max-line-length = 120", content)

    def test_readme_claims_match_implementation(self):
        """README must specify Python 3.11+ and PyWebView 5.0+."""
        readme_path = Path("README.md")
        content = readme_path.read_text(encoding="utf-8")
        self.assertIn("PyWebView 5.0+", content)
        self.assertIn("Python 3.11+", content)


if __name__ == "__main__":
    unittest.main()
