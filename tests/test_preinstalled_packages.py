"""Check source recovery and rootfs transaction interception without cross-compiling."""
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

    def test_prepare_reuses_source_and_hooks_opkg_once(self):
        for directory in ["scripts", "feeds/luci/themes/luci-theme-vantage", "package"]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "feeds/luci/themes/luci-theme-vantage/Makefile").touch()
        (self.root / ".config").write_text("CONFIG_USE_APK=y\n")
        makefile = self.root / "package/Makefile"
        makefile.write_text('\t$(call apk,$(TARGET_DIR)) add packages\n'
                            '\t$(call opkg,$(TARGET_DIR)) install packages\n')
        for _ in range(2):
            result = self.run_script("prepare", env=dict(os.environ, WRT_THEME="vantage"))
            self.assertEqual(result.returncode, 0, result.stderr)
        text = makefile.read_text()
        self.assertEqual(text.count('check-preinstalled.sh" opkg env'), 1)
        # APK stays untouched: its --simulate rejects a fresh-root dry run.
        self.assertEqual(text.count('check-preinstalled.sh" apk env'), 0)
        self.assertIn('\t$(call apk,$(TARGET_DIR)) add packages\n', text)

    def test_missing_dependency_blocks_actual_install(self):
        solver = self.root / "solver.sh"
        solver.write_text('printf "%s\\n" "$*" >> calls\n'
                          'case "$*" in *--noaction*)\n'
                          'test -f theme-present || { echo "luci-theme-vantage (no such package)" >&2; exit 1; };; esac\n')
        for available in [False, True]:
            with self.subTest(available=available):
                (self.root / "calls").unlink(missing_ok=True)
                theme = self.root / "theme-present"
                theme.unlink(missing_ok=True)
                if available:
                    theme.touch()
                result = self.run_script("opkg", BASH, str(solver), "install", "luci-light")
                self.assertEqual(result.returncode, 0 if available else 1, result.stderr)
                calls = (self.root / "calls").read_text().splitlines()
                self.assertEqual(len(calls), 2 if available else 1)
                if not available:
                    self.assertIn("luci-theme-vantage", result.stderr)
