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

    def test_prepare_reuses_source_and_hooks_both_managers_once(self):
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
        for manager in ["apk", "opkg"]:
            self.assertEqual(makefile.read_text().count('check-preinstalled.sh" ' + manager + ' env'), 1)

    def test_missing_dependency_blocks_actual_install(self):
        solver = self.root / "solver.sh"
        solver.write_text('printf "%s\\n" "$*" >> calls\n'
                          'case "$*" in *--simulate*|*--noaction*)\n'
                          'test -f theme-present || { echo "luci-theme-vantage (no such package)" >&2; exit 1; };; esac\n')
        for manager in ["apk", "opkg"]:
            for available in [False, True]:
                with self.subTest(manager=manager, available=available):
                    (self.root / "calls").unlink(missing_ok=True)
                    theme = self.root / "theme-present"
                    theme.unlink(missing_ok=True)
                    if available:
                        theme.touch()
                    result = self.run_script(manager, BASH, str(solver), "--root", str(self.root / "rootfs"), "install", "luci-light")
                    self.assertEqual(result.returncode, 0 if available else 1, result.stderr)
                    calls = (self.root / "calls").read_text().splitlines()
                    self.assertEqual(len(calls), 2 if available else 1)
                    if not available:
                        self.assertIn("luci-theme-vantage", result.stderr)

    @unittest.skipUnless(os.environ.get("APK_TEST_BINARY"), "set APK_TEST_BINARY to a real APK executable")
    def test_real_apk_on_fresh_root(self):
        apk = os.environ["APK_TEST_BINARY"]
        root = self.root / "rootfs"
        root.mkdir()
        command = [apk, "--root", str(root), "--allow-untrusted", "--no-cache",
                   "--repositories-file", "/dev/null", "add", "--initdb", "--no-scripts"]
        # This fails without the bootstrap: --simulate disables --initdb.
        result = self.run_script("apk", *command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / "etc/apk/world").exists())
        result = self.run_script("apk", *command, "luci-theme-vantage")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("luci-theme-vantage", result.stderr)
        self.assertNotIn("Unable to read database", result.stderr)
        self.assertEqual((root / "etc/apk/world").read_text().strip(), "")
