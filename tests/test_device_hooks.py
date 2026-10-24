"""Exercise per-device dispatch and AP8220 packaging without a full build."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def bash_executable():
    if os.name == 'nt':
        git = shutil.which('git')
        if git:
            candidate = Path(git).parents[1] / 'usr/bin/sh.exe'
            if candidate.exists():
                return str(candidate)
    return shutil.which('bash') or 'bash'


class DeviceHookTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='test-device-hooks-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repository = Path(__file__).resolve().parents[1]
        scripts = self.root / 'Scripts'
        scripts.mkdir()
        shutil.copyfile(self.repository / 'Scripts/Device.sh', scripts / 'Device.sh')

    def run_hook(self, action, config, cwd=None, extra_env=None):
        env = os.environ.copy()
        env['WRT_CONFIG'] = config
        env['BASH'] = bash_executable()
        if os.name == 'nt':
            env['PATH'] = str(Path(bash_executable()).parent) + ';' + env.get('PATH', '')
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [bash_executable(), (self.root / 'Scripts/Device.sh').as_posix(), action],
            cwd=cwd or self.root, env=env, capture_output=True, text=True, encoding='utf-8',
        )

    def install_ap8220_hook(self):
        (self.root / 'Scripts/Device-Hooks').mkdir()
        shutil.copyfile(
            self.repository / 'Scripts/Device-Hooks/IPQ807X-AP8220-1G-WIFI-NO.sh',
            self.root / 'Scripts/Device-Hooks/IPQ807X-AP8220-1G-WIFI-NO.sh',
        )
        (self.root / 'docs').mkdir()
        shutil.copyfile(self.repository / 'docs/AP8220-1G-NAND-SETUP-COMPAT.md', self.root / 'docs/AP8220-1G-NAND-SETUP-COMPAT.md')
        shutil.copyfile(
            self.repository / 'Scripts/Install-AP8220-1G-From-Transition.sh',
            self.root / 'Scripts/Install-AP8220-1G-From-Transition.sh',
        )

    def test_dispatch_is_a_noop_without_a_matching_hook(self):
        (self.root / 'Scripts/Device-Hooks').mkdir()
        hook = self.root / 'Scripts/Device-Hooks/TEST-DEVICE.sh'
        hook.write_text('#!/bin/bash\nprintf "called %s\\n" "$1"\n', encoding='utf-8', newline='\n')
        other = self.run_hook('prepare', 'OTHER-DEVICE')
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertEqual(other.stdout, '')
        matched = self.run_hook('prepare', 'TEST-DEVICE')
        self.assertEqual(matched.returncode, 0, matched.stderr)
        self.assertEqual(matched.stdout, 'called prepare\n')

    def test_invalid_config_name_is_rejected_before_dispatch(self):
        result = self.run_hook('prepare', '../outside')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Invalid WRT_CONFIG', result.stderr)

    def test_ap8220_package_keeps_device_assets_out_of_other_builds(self):
        self.install_ap8220_hook()
        firmware = self.root / 'firmware'
        upload = firmware / 'upload'
        upload.mkdir(parents=True)
        (upload / 'qualcommax-ipq807x-aliyun_ap8220-squashfs-sysupgrade.bin').write_bytes(b'ap')
        (upload / 'qualcommax-ipq807x-other.bin').write_bytes(b'other')
        github_env = self.root / 'github-env'
        result = self.run_hook(
            'package', 'IPQ807X-AP8220-1G-WIFI-NO', cwd=firmware,
            extra_env={
                'GITHUB_ENV': str(github_env), 'GITHUB_RUN_ID': '123',
                'WRT_REPO': 'repo', 'WRT_BRANCH': 'main', 'WRT_HASH': 'abc',
                'WRT_IP': '192.168.1.1',
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((upload / 'qualcommax-ipq807x-aliyun_ap8220-1g-squashfs-sysupgrade.bin').exists())
        self.assertTrue((upload / 'qualcommax-ipq807x-other.bin').exists())
        self.assertTrue((upload / 'AP8220-1G-NAND-SETUP-COMPAT.md').exists())
        self.assertTrue((upload / 'Install-AP8220-1G-From-Transition.sh').exists())
        checksums = upload / 'SHA256SUMS.txt'
        if checksums.exists():
            self.assertNotIn('SHA256SUMS.txt', checksums.read_text(encoding='utf-8'))
        self.assertIn('AP8220 1 GiB NAND', (firmware / 'release-body.md').read_text(encoding='utf-8'))
        self.assertFalse((upload / 'release-body.md').exists())
        self.assertIn('WRT_ARTIFACT_NAME=AP8220-1G-123', github_env.read_text(encoding='utf-8'))

    def test_ap8220_verification_rejects_missing_nss(self):
        self.install_ap8220_hook()
        firmware = self.root / 'firmware'
        firmware.mkdir()
        base = (
            'CONFIG_TARGET_DEVICE_qualcommax_ipq807x_DEVICE_aliyun_ap8220=y\n'
            'CONFIG_TARGET_ROOTFS_INITRAMFS=y\n'
            'CONFIG_TARGET_ROOTFS_SQUASHFS=y\n'
            'CONFIG_PACKAGE_nss-firmware=y\n'
            'CONFIG_PACKAGE_kmod-qca-nss-drv=y\n'
            'CONFIG_PACKAGE_kmod-qca-nss-ecm=y\n'
            'CONFIG_PACKAGE_kmod-qca-nss-dp=y\n'
            'CONFIG_PACKAGE_kmod-qca-ssdk=y\n'
        )
        config = firmware / '.config'
        config.write_text(base, encoding='utf-8')
        good = self.run_hook('verify', 'IPQ807X-AP8220-1G-WIFI-NO', cwd=firmware, extra_env={'WRT_BRANCH': 'main'})
        self.assertEqual(good.returncode, 0, good.stderr)
        config.write_text(base.replace('CONFIG_PACKAGE_nss-firmware=y\n', ''), encoding='utf-8')
        bad = self.run_hook('verify', 'IPQ807X-AP8220-1G-WIFI-NO', cwd=firmware, extra_env={'WRT_BRANCH': 'main'})
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('NSS is not selected', bad.stderr)


if __name__ == '__main__':
    unittest.main()
