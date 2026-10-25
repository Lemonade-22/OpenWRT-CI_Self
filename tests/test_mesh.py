"""Exercise provider replacement and the post-defconfig dependency gate."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class MeshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = Path(__file__).resolve().parents[1] / 'Scripts/Mesh.sh'
        hostapd = self.root / 'package/network/services/hostapd/Makefile'
        hostapd.parent.mkdir(parents=True)
        hostapd.write_text('\n'.join('define Package/' + name for name in (
            'wpad-openssl', 'wpad-basic-mbedtls', 'wpad-mesh-openssl',
            'hostapd-openssl', 'wpa-supplicant-openssl', 'hostapd-common',
            'hostapd-utils',
        )) + '\n')
        self.config = self.root / '.config'
        self.config.write_text(
            'CONFIG_PACKAGE_wpad-basic-mbedtls=y\n'
            'CONFIG_PACKAGE_hostapd-openssl=y\n'
            'CONFIG_PACKAGE_hostapd-utils=y\n'
            '# CONFIG_PACKAGE_MAC80211_MESH is not set\n'
            'CONFIG_PACKAGE_luci-app-mesh=m\n'
            'CONFIG_TARGET_ramips=y\n'
        )

    def run_mesh(self, mode):
        return subprocess.run(['bash', str(self.script), mode], cwd=self.root,
                              capture_output=True, text=True)

    def test_replace_conflicts_preserve_utilities_and_repeat_safely(self):
        self.assertEqual(self.run_mesh('configure').returncode, 0)
        config = self.config.read_text()
        self.assertIn('# CONFIG_PACKAGE_wpad-basic-mbedtls is not set', config)
        self.assertIn('# CONFIG_PACKAGE_hostapd-openssl is not set', config)
        self.assertIn('CONFIG_PACKAGE_hostapd-utils=y', config)
        self.assertIn('CONFIG_TARGET_ramips=y', config)
        self.assertIn('CONFIG_PACKAGE_MAC80211_MESH=y', config)
        self.assertNotIn('CONFIG_PACKAGE_luci-app-mesh=m', config)
        self.assertEqual(self.run_mesh('configure').returncode, 0)
        self.assertEqual(self.config.read_text(), config)
        self.assertEqual(self.run_mesh('verify').returncode, 0)

    def test_missing_kernel_dependency_is_rejected(self):
        self.assertEqual(self.run_mesh('configure').returncode, 0)
        self.config.write_text(self.config.read_text().replace(
            'CONFIG_PACKAGE_kmod-batman-adv=y\n', ''))
        result = self.run_mesh('verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('kmod-batman-adv', result.stderr)

    def test_reselected_provider_is_rejected(self):
        self.assertEqual(self.run_mesh('configure').returncode, 0)
        with self.config.open('a') as output:
            output.write('CONFIG_PACKAGE_wpad-basic-mbedtls=y\n')
        self.assertNotEqual(self.run_mesh('verify').returncode, 0)
