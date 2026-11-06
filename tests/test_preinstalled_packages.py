"""Check theme source recovery without cross-compiling."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
if os.name == "nt":
    BASH = "C:/Program Files/Git/bin/bash.exe" if Path("C:/Program Files/Git/bin/bash.exe").exists() else None


@unittest.skipUnless(BASH, "bash required")
class PreinstalledPackages(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = ROOT / "Scripts/Check-Preinstalled.sh"

    def run_script(self, *args, **kwargs):
        return subprocess.run([BASH, str(self.script), *args], cwd=self.root,
                              capture_output=True, text=True, **kwargs)

    def test_prepare_reuses_existing_theme_source(self):
        for directory in ["scripts", "feeds/luci/themes/luci-theme-vantage", "package"]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "feeds/luci/themes/luci-theme-vantage/Makefile").touch()
        makefile = self.root / "package/Makefile"
        original = '\t$(call apk,$(TARGET_DIR)) add packages\n' \
                   '\t$(call opkg,$(TARGET_DIR)) install packages\n'
        makefile.write_text(original)
        for _ in range(2):
            result = self.run_script("prepare", env=dict(os.environ, WRT_THEME="vantage"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("luci-theme-vantage", result.stdout)
        # No package-manager hook is installed any more.
        self.assertEqual(makefile.read_text(), original)
        self.assertFalse((self.root / "scripts/check-preinstalled.sh").exists())

    def test_missing_theme_source_fails_before_defconfig(self):
        for directory in ["scripts", "feeds", "package"]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        # A feed that installs nothing must still fail loudly instead of dropping the theme.
        feeds = self.root / "scripts/feeds"
        feeds.write_text('#!/bin/bash\nexit 0\n')
        feeds.chmod(0o755)
        result = self.run_script("prepare", env=dict(os.environ, WRT_THEME="nonesuch"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing luci-theme-nonesuch", result.stderr)

    def test_usage_rejects_the_removed_hook_mode(self):
        result = self.run_script("opkg", "true")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ", result.stderr)
