"""Exercise selectors surviving defconfig and the final Linux config release gate."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Scripts/kernel_compat.py'
spec = importlib.util.spec_from_file_location('kernel_compat', SCRIPT)
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class CompatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'config').mkdir()
        (self.root / 'config/Config-kernel.in').write_text(
            'config KERNEL_NET_NS\n\tbool "Network namespaces"\n\tdefault n\n')
        (self.root / '.config').write_text(
            'CONFIG_aarch64=y\n# CONFIG_KERNEL_COMPAT is not set\nCONFIG_KERNEL_COMPAT=n\n')

    def run_phase(self, phase):
        return subprocess.run([sys.executable, str(SCRIPT), phase], cwd=self.root,
                              capture_output=True, text=True)

    def test_configure_replaces_overrides_and_registers_missing_selectors(self):
        self.assertEqual(self.run_phase('configure').returncode, 0)
        first = (self.root / '.config').read_text()
        definitions = (self.root / 'config/Config-kernel.in').read_text()
        self.assertEqual(first.count('CONFIG_KERNEL_COMPAT=y'), 1)
        self.assertIn('depends on aarch64', definitions)
        self.assertEqual(definitions.count('config KERNEL_NET_NS\n'), 1)
        self.assertIn('config KERNEL_SYSVIPC', definitions)
        self.assertEqual(self.run_phase('configure').returncode, 0)
        self.assertEqual((self.root / '.config').read_text(), first)
        self.assertEqual((self.root / 'config/Config-kernel.in').read_text(), definitions)
        self.assertEqual(self.run_phase('verify').returncode, 0)

    def test_defconfig_dropping_compat_fails_on_arm64(self):
        self.run_phase('configure')
        config = self.root / '.config'
        config.write_text(config.read_text().replace('CONFIG_KERNEL_COMPAT=y',
                                                    '# CONFIG_KERNEL_COMPAT is not set'))
        result = self.run_phase('verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('COMPAT=y', result.stderr)

    def test_compat_children_have_explicit_answers_before_linux_syncconfig(self):
        self.assertEqual(self.run_phase('configure').returncode, 0)
        text = (self.root / '.config').read_text()
        definitions = (self.root / 'config/Config-kernel.in').read_text()
        # Regression: enabling COMPAT exposes this prompt and Linux syncconfig
        # exits in non-interactive CI when no answer was provided.
        for symbol in ('KUSER_HELPERS', 'COMPAT_ALIGNMENT_FIXUPS'):
            self.assertIn('CONFIG_KERNEL_' + symbol + '=y\n', text)
            self.assertIn('config KERNEL_' + symbol + '\n', definitions)

    def test_deprecated_instruction_prompt_has_an_explicit_default_answer(self):
        # COMPAT exposes ARMV8_DEPRECATED even after its two direct child
        # options are answered. OpenWrt copies disabled CONFIG_KERNEL_* lines
        # into Linux .config.target as well as enabled ones.
        config = self.root / '.config'
        config.write_text(config.read_text() + 'CONFIG_KERNEL_ARMV8_DEPRECATED=y\n')
        self.assertEqual(self.run_phase('configure').returncode, 0)
        text = config.read_text()
        self.assertIn('# CONFIG_KERNEL_ARMV8_DEPRECATED is not set\n', text)
        self.assertNotIn('CONFIG_KERNEL_ARMV8_DEPRECATED=y', text)
        definitions = (self.root / 'config/Config-kernel.in').read_text()
        self.assertIn('config KERNEL_ARMV8_DEPRECATED\n\tbool\n'
                      '\tdepends on aarch64\n\tdefault n\n', definitions)
        self.assertEqual(self.run_phase('configure').returncode, 0)
        self.assertEqual(config.read_text(), text)

    def test_compat_integer_prompt_is_answered_before_syncconfig(self):
        # Regression: enabling COMPAT exposes ARCH_MMAP_RND_COMPAT_BITS, which
        # is a range-limited integer prompt. Answering only booleans leaves it
        # unanswered, so Linux syncconfig turns interactive and aborts the
        # kernel build in CI.
        self.assertEqual(self.run_phase('configure').returncode, 0)
        text = (self.root / '.config').read_text()
        definitions = (self.root / 'config/Config-kernel.in').read_text()
        self.assertIn('CONFIG_KERNEL_ARCH_MMAP_RND_COMPAT_BITS=11\n', text)
        self.assertIn('config KERNEL_ARCH_MMAP_RND_COMPAT_BITS\n\tint\n'
                      '\tdepends on aarch64\n\tdefault 11\n', definitions)
        self.assertEqual(self.run_phase('verify').returncode, 0)

    def test_defconfig_dropping_compat_aslr_value_fails_on_arm64(self):
        self.run_phase('configure')
        config = self.root / '.config'
        config.write_text(config.read_text().replace(
            'CONFIG_KERNEL_ARCH_MMAP_RND_COMPAT_BITS=11\n', ''))
        result = self.run_phase('verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARCH_MMAP_RND_COMPAT_BITS=11', result.stderr)

    def test_final_kernel_gate_catches_dropped_aslr_value(self):
        self.run_phase('configure')
        path = self.root / 'build_dir/target-aarch64/linux-mediatek_filogic/linux-6.18/.config'
        path.parent.mkdir(parents=True)
        full = ''.join('CONFIG_' + symbol + '=y\n' for symbol in compat.ARM64)
        full += 'CONFIG_ARCH_MMAP_RND_COMPAT_BITS=11\n'
        path.write_text(full.replace('CONFIG_ARCH_MMAP_RND_COMPAT_BITS=11\n', ''))
        result = self.run_phase('verify-kernel')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARCH_MMAP_RND_COMPAT_BITS=11', result.stderr)
        path.write_text(full)
        self.assertEqual(self.run_phase('verify-kernel').returncode, 0)

    def test_final_kernel_gate_catches_dropped_compat_and_ipc(self):
        self.run_phase('configure')
        path = self.root / 'build_dir/target-aarch64/linux-mediatek_filogic/linux-6.18/.config'
        path.parent.mkdir(parents=True)
        full = ''.join('CONFIG_' + symbol + '=y\n' for symbol in compat.ARM64)
        full += 'CONFIG_ARCH_MMAP_RND_COMPAT_BITS=11\n'
        for symbol in ('COMPAT', 'SYSVIPC', 'IPC_NS'):
            path.write_text(full.replace('CONFIG_' + symbol + '=y\n', ''))
            result = self.run_phase('verify-kernel')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(symbol + '=y', result.stderr)
        path.write_text(full)
        self.assertEqual(self.run_phase('verify-kernel').returncode, 0)

    def test_32bit_target_does_not_require_compat(self):
        self.run_phase('configure')
        config = self.root / '.config'
        config.write_text(config.read_text().replace('CONFIG_aarch64=y\n', '')
                          .replace('CONFIG_KERNEL_COMPAT=y\n', ''))
        self.assertEqual(self.run_phase('verify').returncode, 0)

    def test_missing_compiled_kernel_is_an_error(self):
        self.run_phase('configure')
        self.assertNotEqual(self.run_phase('verify-kernel').returncode, 0)


if __name__ == '__main__':
    unittest.main()
