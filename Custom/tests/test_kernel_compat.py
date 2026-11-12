"""Exercise the honk TCX selectors surviving defconfig and the final kernel gate."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'Scripts/kernel_compat.py'
spec = importlib.util.spec_from_file_location('kernel_compat', SCRIPT)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class TcxTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/Config-kernel.in').write_text(
            'config KERNEL_NET_NS\n\tbool "Network namespaces"\n\tdefault n\n')
        self.config = self.root / '.config'
        self.config.write_text('CONFIG_TARGET_ipq60xx=y\n')
        self.kernel = self.root / 'build_dir/target-aarch64/linux-mediatek_filogic/linux-6.18/.config'

    def run_phase(self, phase):
        return subprocess.run([sys.executable, str(SCRIPT), phase], cwd=self.root,
                              capture_output=True, text=True)

    def write_kernel(self, symbols=None):
        symbols = compat.TCX if symbols is None else symbols
        self.kernel.parent.mkdir(parents=True, exist_ok=True)
        self.kernel.write_text(''.join('CONFIG_' + symbol + '=y\n' for symbol in symbols))

    def test_configure_registers_the_selectors_and_is_idempotent(self):
        self.assertEqual(self.run_phase('configure').returncode, 0)
        first = self.config.read_text()
        definitions = (self.root / 'config/Config-kernel.in').read_text()
        for symbol in compat.TCX:
            self.assertIn('CONFIG_KERNEL_' + symbol + '=y\n', first)
            self.assertIn('config KERNEL_' + symbol + '\n\tbool\n\tdefault y\n', definitions)
        self.assertEqual(self.run_phase('configure').returncode, 0)
        self.assertEqual(self.config.read_text(), first)
        self.assertEqual((self.root / 'config/Config-kernel.in').read_text(), definitions)

    def test_verify_passes_after_configure(self):
        self.assertEqual(self.run_phase('configure').returncode, 0)
        result = self.run_phase('verify')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_defconfig_dropping_a_selector_fails_verify(self):
        self.run_phase('configure')
        for symbol in compat.TCX:
            self.config.write_text(self.config.read_text().replace(
                'CONFIG_KERNEL_' + symbol + '=y\n',
                '# CONFIG_KERNEL_' + symbol + ' is not set\n'))
            result = self.run_phase('verify')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(symbol + '=y', result.stderr)

    def test_final_kernel_gate_catches_a_dropped_selector(self):
        self.run_phase('configure')
        self.write_kernel(symbols=(compat.TCX[0],))
        result = self.run_phase('verify-kernel')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(compat.TCX[1] + '=y', result.stderr)
        self.write_kernel()
        result = self.run_phase('verify-kernel')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Verified honk TCX', result.stdout)

    def test_missing_compiled_kernel_is_an_error(self):
        self.run_phase('configure')
        self.assertNotEqual(self.run_phase('verify-kernel').returncode, 0)

    def test_ramips_keeps_its_own_kernel_untouched(self):
        # mt7621 still ships an older kernel, so the whole layer must stay off
        # and the build must come out byte-identical.
        self.config.write_text('CONFIG_TARGET_ramips=y\n'
                               'CONFIG_TARGET_ramips_mt7621=y\n')
        original_config = self.config.read_text()
        definitions = self.root / 'config/Config-kernel.in'
        original_definitions = definitions.read_text()
        self.write_kernel()
        for phase in ('configure', 'verify', 'verify-kernel'):
            result = self.run_phase(phase)
            self.assertEqual(result.returncode, 0, phase)
            self.assertIn('skipped', result.stdout, phase)
        self.assertEqual(self.config.read_text(), original_config)
        self.assertEqual(definitions.read_text(), original_definitions)

    def test_missing_config_file_skips_the_layer(self):
        self.config.unlink()
        for phase in ('configure', 'verify', 'verify-kernel'):
            self.assertEqual(self.run_phase(phase).returncode, 0, phase)


if __name__ == '__main__':
    unittest.main()
