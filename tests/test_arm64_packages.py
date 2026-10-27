import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packages', ROOT / 'Custom/ARM64-OPhub/verify_packages.py')
packages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packages)


class PackageTests(unittest.TestCase):
    def test_vantage_has_dashboard_but_no_config_package(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage=y\nCONFIG_PACKAGE_luci-app-vantage-config=y\n'
        defined = 'config PACKAGE_luci-app-vantage\n'
        self.assertEqual(packages.missing(requested, 'CONFIG_PACKAGE_luci-app-vantage=y\n', defined, 'vantage'), [])

    def test_existing_theme_package_must_not_disappear(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage=y\n'
        self.assertEqual(packages.missing(requested, '', 'config PACKAGE_luci-app-vantage\n', 'vantage'), requested.splitlines())

    def test_unrelated_missing_plugin_is_still_an_error(self):
        requested = 'CONFIG_PACKAGE_luci-app-homeproxy=y\n'
        self.assertEqual(packages.missing(requested, '', '', 'vantage'), requested.splitlines())


class ThemeCompanionTests(unittest.TestCase):
    # Upstream data verified against VIKINGYFY/immortalwrt Scripts/Settings.sh
    # (the three unconditional CONFIG_PACKAGE_* theme echoes) and the vantage
    # feed Makefiles (PKG_NAME:=luci-app-vantage, PKG_NAME:=luci-theme-vantage;
    # no luci-app-vantage-config package exists).
    VANTAGE_REQUESTED = (
        'CONFIG_PACKAGE_luci-theme-vantage=y\n'
        'CONFIG_PACKAGE_luci-app-vantage=y\n'
        'CONFIG_PACKAGE_luci-app-vantage-config=y\n'
    )
    VANTAGE_DEFINITIONS = (
        'config PACKAGE_luci-theme-vantage\n'
        'config PACKAGE_luci-app-vantage\n'
    )
    VANTAGE_ACTUAL = (
        'CONFIG_PACKAGE_luci-theme-vantage=y\n'
        'CONFIG_PACKAGE_luci-app-vantage=y\n'
    )

    def test_vantage_matches_upstream_data(self):
        dropped, skipped = packages.evaluate(
            self.VANTAGE_REQUESTED,
            self.VANTAGE_ACTUAL,
            self.VANTAGE_DEFINITIONS,
            'vantage',
        )
        self.assertEqual(dropped, [])
        self.assertEqual(skipped, ['luci-app-vantage-config'])
        self.assertEqual(
            packages.missing(
                self.VANTAGE_REQUESTED,
                self.VANTAGE_ACTUAL,
                self.VANTAGE_DEFINITIONS,
                'vantage',
            ),
            [],
        )

    def test_undefined_companion_is_skipped_not_failed(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage-config=y\n'
        self.assertEqual(packages.missing(requested, '', '', 'vantage'), [])
        self.assertEqual(
            packages.evaluate(requested, '', '', 'vantage'),
            ([], ['luci-app-vantage-config']),
        )

    def test_defined_but_dropped_config_companion_fails(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage-config=y\n'
        definitions = 'config PACKAGE_luci-app-vantage-config\n'
        self.assertEqual(
            packages.missing(requested, '', definitions, 'vantage'),
            requested.splitlines(),
        )

    def test_defined_theme_app_companion_dropped_fails(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage=y\n'
        definitions = 'config PACKAGE_luci-app-vantage\n'
        actual = 'CONFIG_PACKAGE_luci-theme-vantage=y\n'
        self.assertEqual(
            packages.missing(requested, actual, definitions, 'vantage'),
            requested.splitlines(),
        )

    def test_missing_theme_package_still_fails(self):
        requested = 'CONFIG_PACKAGE_luci-theme-vantage=y\n'
        definitions = 'config PACKAGE_luci-theme-vantage\n'
        self.assertEqual(
            packages.missing(requested, '', definitions, 'vantage'),
            requested.splitlines(),
        )

    def test_defined_companions_that_survive_pass(self):
        # Both companions defined by the feeds and present after defconfig:
        # nothing may be reported as dropped or skipped.
        requested = (
            'CONFIG_PACKAGE_luci-theme-vantage=y\n'
            'CONFIG_PACKAGE_luci-app-vantage=y\n'
            'CONFIG_PACKAGE_luci-app-vantage-config=y\n'
        )
        definitions = (
            'config PACKAGE_luci-app-vantage\n'
            'config PACKAGE_luci-app-vantage-config\n'
        )
        actual = requested
        dropped, skipped = packages.evaluate(requested, actual, definitions, 'vantage')
        self.assertEqual(dropped, [])
        self.assertEqual(skipped, [])

    def test_defined_but_dropped_non_theme_package_still_fails(self):
        requested = 'CONFIG_PACKAGE_luci-app-homeproxy=y\n'
        definitions = 'config PACKAGE_luci-app-homeproxy\n'
        self.assertEqual(
            packages.missing(requested, '', definitions, 'vantage'),
            requested.splitlines(),
        )

    def test_dropped_lines_keep_input_order(self):
        requested = (
            'CONFIG_PACKAGE_luci-app-alpha=y\n'
            'CONFIG_PACKAGE_luci-app-beta=y\n'
            'CONFIG_PACKAGE_luci-app-gamma=y\n'
        )
        actual = 'CONFIG_PACKAGE_luci-app-beta=y\n'
        self.assertEqual(
            packages.missing(requested, actual, '', 'vantage'),
            [
                'CONFIG_PACKAGE_luci-app-alpha=y',
                'CONFIG_PACKAGE_luci-app-gamma=y',
            ],
        )

    def test_blank_and_comment_lines_are_ignored(self):
        requested = '\n# upstream selection\nCONFIG_PACKAGE_luci=y\n\n'
        actual = 'CONFIG_PACKAGE_luci=y\n'
        self.assertEqual(packages.missing(requested, actual, '', 'vantage'), [])


class VerifyPackagesCliTests(unittest.TestCase):
    def _run_cli(self, requested, actual, definitions, theme='vantage'):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, body in (
                ('requested.config', requested),
                ('actual.config', actual),
                ('definitions.in', definitions),
            ):
                path = Path(tmp) / name
                path.write_text(body, encoding='utf-8')
                paths[name] = path

            return subprocess.run(
                [
                    sys.executable,
                    str(ROOT / 'Custom/ARM64-OPhub/verify_packages.py'),
                    '--requested',
                    str(paths['requested.config']),
                    '--actual',
                    str(paths['actual.config']),
                    '--definitions',
                    str(paths['definitions.in']),
                    '--theme',
                    theme,
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )

    def test_cli_passes_and_reports_skipped_companion(self):
        result = self._run_cli(
            ThemeCompanionTests.VANTAGE_REQUESTED,
            ThemeCompanionTests.VANTAGE_ACTUAL,
            ThemeCompanionTests.VANTAGE_DEFINITIONS,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            'Skipping absent theme companion package luci-app-vantage-config '
            '(not defined by the selected feeds)',
            result.stdout,
        )
        self.assertNotIn('::error::', result.stdout + result.stderr)

    def test_cli_fails_for_defined_but_dropped_package(self):
        requested = 'CONFIG_PACKAGE_luci-app-vantage-config=y\n'
        definitions = 'config PACKAGE_luci-app-vantage-config\n'
        result = self._run_cli(requested, '', definitions)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            '::error::Upstream LuCI package was dropped: '
            'CONFIG_PACKAGE_luci-app-vantage-config=y',
            result.stdout,
        )

    def test_cli_passes_without_skip_when_everything_survives(self):
        requested = (
            'CONFIG_PACKAGE_luci-theme-vantage=y\n'
            'CONFIG_PACKAGE_luci-app-vantage=y\n'
        )
        result = self._run_cli(requested, requested, ThemeCompanionTests.VANTAGE_DEFINITIONS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Skipping absent theme companion', result.stdout)
        self.assertIn('All selected upstream LuCI packages are present', result.stdout)


if __name__ == '__main__':
    unittest.main()
