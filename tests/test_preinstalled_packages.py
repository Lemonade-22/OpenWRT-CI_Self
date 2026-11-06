"""Check theme source provisioning without cross-compiling."""
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
        for directory in ["scripts", "package", "feeds/luci/themes"]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def run_script(self, *args, **kwargs):
        env = dict(os.environ)
        env["WRT_THEME"] = "vantage"
        env.update(kwargs.pop("env", {}))
        return subprocess.run([BASH, str(self.script), *args], cwd=self.root,
                              capture_output=True, text=True, env=env, **kwargs)

    def add_feed_theme(self, theme="vantage"):
        directory = self.root / f"feeds/luci/themes/luci-theme-{theme}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "Makefile").touch()

    def test_theme_already_in_the_feed_is_used_as_is(self):
        self.add_feed_theme()
        result = self.run_script("prepare")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("luci-theme-vantage", result.stdout)
        self.assertFalse((self.root / "package/luci-theme-vantage").exists())

    def test_missing_theme_is_cloned_from_the_table(self):
        table = self.root / "themes.txt"
        table.write_text("# theme repo branch\nvantage anothaDev/luci-theme-vantage main\n")
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_git.write_text(
            '#!/bin/bash\n'
            'dest="${@: -1}"\n'
            'mkdir -p "$dest/luci-theme-vantage"\n'
            'touch "$dest/luci-theme-vantage/Makefile"\n'
        )
        fake_git.chmod(0o755)
        result = self.run_script("prepare", env={"THEME_TABLE": str(table),
                                                 "PATH": f"{fake_bin}:{os.environ.get('PATH','')}"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cloning anothaDev/luci-theme-vantage", result.stderr)
        self.assertTrue((self.root / "package/luci-theme-vantage/luci-theme-vantage/Makefile").exists())

    def test_theme_without_any_source_fails_before_defconfig(self):
        table = self.root / "themes.txt"
        table.write_text("# nothing useful\n")
        feeds = self.root / "scripts/feeds"
        feeds.write_text("#!/bin/bash\nexit 0\n")
        feeds.chmod(0o755)
        result = self.run_script("prepare", env={"THEME_TABLE": str(table), "WRT_THEME": "newtheme"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot build luci-theme-newtheme", result.stderr)
        self.assertIn("Scripts/themes.txt", result.stderr)

    def test_unresolved_auto_theme_is_rejected(self):
        result = self.run_script("prepare", env={"WRT_THEME": "auto"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be resolved first", result.stderr)

    def test_usage_rejects_the_removed_hook_mode(self):
        result = self.run_script("opkg", "true")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ", result.stderr)
