"""Exercise generation against actual workflow/patch files with real git apply."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class CoreGenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='test-wrt-core-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        repository = Path(__file__).resolve().parents[1]
        for name in (
            'Scripts/Generate-Wrt-Core.py',
            'patches/wrt-core-self.patch',
            'patches/wrt-core-ap8220.patch',
            '.github/workflows/WRT-CORE.yml',
            '.github/workflows/WRT-CORE-SELF.yml',
            '.github/workflows/AP8220-CORE.yml',
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / name, destination)
        self.source = self.root / '.github/workflows/WRT-CORE.yml'
        self.output = self.root / '.github/workflows/WRT-CORE-SELF.yml'
        self.ap_output = self.root / '.github/workflows/AP8220-CORE.yml'

    def run_generator(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / 'Scripts/Generate-Wrt-Core.py'), *args],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8',
        )

    def test_checked_in_workflow_is_reproducible_without_changing_upstream(self):
        source = self.source.read_bytes()
        expected = self.output.read_text(encoding='utf-8')
        expected_ap = self.ap_output.read_text(encoding='utf-8')
        self.output.unlink()
        self.ap_output.unlink()
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(encoding='utf-8'), expected)
        self.assertEqual(self.ap_output.read_text(encoding='utf-8'), expected_ap)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.run_generator('--check').returncode, 0)

    def test_upstream_change_outside_patch_is_propagated(self):
        content = self.source.read_text(encoding='utf-8')
        self.assertIn('            echo "WRT_KVER=none"', content)
        content = content.replace('            echo "WRT_KVER=none"', '            echo "WRT_KVER=unknown"')
        self.source.write_text(content, encoding='utf-8', newline='\n')
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output.read_text(encoding='utf-8')
        self.assertIn('            echo "WRT_KVER=unknown"', generated)
        self.assertNotIn('AP8220', generated)
        self.assertIn('Scripts/Fakeflow.sh', generated)
        ap_generated = self.ap_output.read_text(encoding='utf-8')
        self.assertIn('            echo "WRT_KVER=unknown"', ap_generated)
        self.assertIn('Apply AP8220 1G NAND adaptation', ap_generated)

    def test_patch_conflict_does_not_replace_workflow(self):
        previous = self.output.read_bytes()
        content = self.source.read_text(encoding='utf-8')
        self.assertIn('name: WRT-CORE\n', content)
        self.source.write_text(content.replace('name: WRT-CORE\n', 'name: UPSTREAM-RENAMED\n'), encoding='utf-8', newline='\n')
        result = self.run_generator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('conflicts with WRT-CORE.yml', result.stdout)
        self.assertEqual(self.output.read_bytes(), previous)

    def test_ap8220_patch_conflict_does_not_replace_either_workflow(self):
        previous = (self.output.read_bytes(), self.ap_output.read_bytes())
        patch = self.root / 'patches/wrt-core-ap8220.patch'
        content = patch.read_text(encoding='utf-8')
        self.assertIn('-name: WRT-CORE-SELF\n', content)
        patch.write_text(content.replace('-name: WRT-CORE-SELF\n', '-name: UNKNOWN-CORE\n'), encoding='utf-8', newline='\n')
        result = self.run_generator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('wrt-core-ap8220.patch conflicts', result.stdout)
        self.assertEqual((self.output.read_bytes(), self.ap_output.read_bytes()), previous)

    def test_ap8220_steps_only_exist_in_the_dedicated_workflow(self):
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        common = self.output.read_text(encoding='utf-8')
        dedicated = self.ap_output.read_text(encoding='utf-8')
        self.assertNotIn('AP8220', common)
        for name in ('Apply AP8220 1G NAND adaptation', 'Verify AP8220 1G image layout',
                     'Package AP8220 installation guide', 'Save AP8220 build artifacts', 'Release AP8220 firmware'):
            self.assertIn(f'- name: {name}\n', dedicated)
        self.assertIn('- name: Release Firmware\n', common)
        self.assertNotIn('- name: Release Firmware\n', dedicated)

    def test_only_ap8220_entry_calls_the_dedicated_workflow(self):
        workflows = Path(__file__).resolve().parents[1] / '.github/workflows'
        callers = [path.name for path in workflows.glob('*.yml')
                   if 'uses: ./.github/workflows/AP8220-CORE.yml' in path.read_text(encoding='utf-8')]
        self.assertEqual(callers, ['AP8220-1G.yml'])

    def test_check_detects_stale_workflow_without_rewriting_it(self):
        self.output.write_text('stale workflow\n', encoding='utf-8')
        result = self.run_generator('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('is stale', result.stdout)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'stale workflow\n')

    def test_check_detects_stale_ap8220_workflow(self):
        self.ap_output.write_text('stale AP8220 workflow\n', encoding='utf-8')
        result = self.run_generator('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('AP8220-CORE.yml is stale', result.stdout)
        self.assertEqual(self.ap_output.read_text(encoding='utf-8'), 'stale AP8220 workflow\n')


if __name__ == '__main__':
    unittest.main()
