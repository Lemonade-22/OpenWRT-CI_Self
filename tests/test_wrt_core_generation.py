"""Exercise workflow generation with the real upstream file and git apply."""

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
        self.repository = Path(__file__).resolve().parents[1]
        for name in (
            'Scripts/Generate-Wrt-Core.py',
            'patches/wrt-core-self.patch',
            '.github/workflows/WRT-CORE.yml',
            '.github/workflows/WRT-CORE-SELF.yml',
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repository / name, destination)
        self.source = self.root / '.github/workflows/WRT-CORE.yml'
        self.output = self.root / '.github/workflows/WRT-CORE-SELF.yml'

    def run_generator(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / 'Scripts/Generate-Wrt-Core.py'), *args],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8',
        )

    def test_checked_in_workflow_is_reproducible_without_changing_upstream(self):
        source = self.source.read_bytes()
        expected = self.output.read_text(encoding='utf-8')
        self.output.unlink()
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(encoding='utf-8'), expected)
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.run_generator('--check').returncode, 0)

    def test_upstream_build_preparation_and_reports_survive_customization(self):
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output.read_text(encoding='utf-8')
        ordered = (
            'Scripts/Handles.sh',
            '.github/scripts/prepare-i2c-tools.sh',
            'Scripts/Mesh.sh" prepare',
            'Scripts/Settings.sh',
            '.github/scripts/prepare-build-host.sh',
            'Scripts/Device.sh" configure',
            'Scripts/Mesh.sh" configure',
            'make defconfig',
            'Scripts/Mesh.sh" verify',
            '.github/scripts/prepare-rust.sh',
            'make download',
            'build-reports/parallel.tsv',
            'build-reports/serial.tsv',
            'Scripts/Device.sh" verify-image',
            '.github/scripts/collect-build-reports.sh',
            '- name: Upload Build Reports',
            '- name: Save Build Cache',
        )
        positions = [generated.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))

    def test_upstream_change_outside_patch_is_propagated(self):
        content = self.source.read_text(encoding='utf-8')
        self.assertIn('            echo "WRT_KVER=none"', content)
        content = content.replace('            echo "WRT_KVER=none"', '            echo "WRT_KVER=unknown"')
        self.source.write_text(content, encoding='utf-8', newline='\n')
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output.read_text(encoding='utf-8')
        self.assertIn('            echo "WRT_KVER=unknown"', generated)
        self.assertIn('Scripts/Device.sh', generated)
        self.assertNotIn('AP8220', generated)

    def test_patch_conflict_does_not_replace_workflow(self):
        previous = self.output.read_bytes()
        content = self.source.read_text(encoding='utf-8')
        self.assertIn('name: WRT-CORE\n', content)
        self.source.write_text(content.replace('name: WRT-CORE\n', 'name: UPSTREAM-RENAMED\n'), encoding='utf-8', newline='\n')
        result = self.run_generator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('conflicts with WRT-CORE.yml', result.stdout)
        self.assertEqual(self.output.read_bytes(), previous)

    def test_check_detects_stale_workflow_without_rewriting_it(self):
        self.output.write_text('stale workflow\n', encoding='utf-8')
        result = self.run_generator('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('is stale', result.stdout)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'stale workflow\n')

    def test_all_build_entries_use_the_same_core(self):
        workflows = self.repository / '.github/workflows'
        callers = {
            path.name for path in workflows.glob('*.yml')
            if 'uses: ./.github/workflows/WRT-CORE-SELF.yml' in path.read_text(encoding='utf-8')
        }
        self.assertEqual(callers, {
            'AP8220-1G.yml', 'MT7621.yml', 'MTK-ALL.yml', 'OWRT-ALL.yml',
            'QCA-ALL.yml', 'QCB-ALL.yml', 'WRT-TEST.yml', 'ZN-M2-WIFI-NO.yml',
        })
        self.assertFalse((workflows / 'AP8220-CORE.yml').exists())


if __name__ == '__main__':
    unittest.main()
