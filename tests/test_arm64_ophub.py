"""Exercise board selection and the actual kernel archive gate without compiling firmware."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'Custom/ARM64-OPhub'


def load(name):
    spec = importlib.util.spec_from_file_location(name, COMMON / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


profiles = load('profiles')
stage_kernel = load('stage_kernel')


class Arm64Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_select_one_or_both_devices(self):
        self.assertEqual([p['board'] for p in profiles.select('all')], ['panther-x2', 'fine3399'])
        self.assertEqual([p['board'] for p in profiles.select('fine3399')], ['fine3399'])
        self.assertEqual(profiles.select('panther-x2')[0]['dtb'], 'rk3566-panther-x2.dtb')
        with self.assertRaises(KeyError):
            profiles.select('unknown-board')
        output = self.root / 'outputs'
        subprocess.run([sys.executable, str(COMMON / 'profiles.py'), '--device', 'fine3399',
                        '--github-output', str(output)], check=True, capture_output=True)
        values = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(json.loads(values['dtbs']), ['rk3399-fine3399.dtb'])
        self.assertEqual(len(json.loads(values['matrix'])['include']), 1)

    def test_locked_recipes_and_boot_files_are_device_specific(self):
        database = self.root / 'model_database.conf'
        # Relevant columns from the pinned OPhub database; CI also checks the real checkout.
        database.write_text(
            'r301:Panther-X2:rk3566:rk3566-panther-x2.dtb:NA:u-boot.itb:idbloader.img:'
            '4GB:stable/6.18.y:rockchip:rk3566:armbianEnv.txt:upstream:panther-x2:yes\n'
            'r416:Fine3399:rk3399:rk3399-fine3399.dtb:trust.bin:uboot.img:idbloader.bin:'
            '4GB:stable/6.18.y:rockchip:rk3399:armbianEnv.txt:upstream:fine3399:yes\n')
        selected = profiles.select('all')
        for profile in selected:
            folder = self.root / 'rockchip' / profile['board']
            folder.mkdir(parents=True)
            for key in ('bootloader', 'uboot', 'trust'):
                if profile[key] != 'NA':
                    (folder / profile[key]).write_bytes(b'boot fixture')
        profiles.validate(selected, database, self.root)
        (self.root / 'rockchip/fine3399/trust.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'trust.bin'):
            profiles.validate(selected, database, self.root)
        profiles.validate(profiles.select('panther-x2'), database, self.root)
        database.write_text(database.read_text().replace('rk3399-fine3399.dtb', 'wrong.dtb'))
        with self.assertRaisesRegex(ValueError, 'upstream dtb differs'):
            profiles.validate(selected, database, self.root)

    def archive(self, dtbs, omit_module=None):
        builtin = ('BPF BPF_SYSCALL BPF_JIT CGROUPS CGROUP_BPF KPROBES KPROBE_EVENTS '
                   'BPF_EVENTS DEBUG_INFO_BTF BPF_STREAM_PARSER XDP_SOCKETS NET_CLS_ACT '
                   'NET_INGRESS NET_EGRESS NET_NS').split()
        modular = {'NET_SCH_INGRESS': 'sch_ingress', 'NET_CLS_BPF': 'cls_bpf',
                   'NET_ACT_BPF': 'act_bpf', 'VETH': 'veth', 'DUMMY': 'dummy', 'TUN': 'tun'}
        config = ''.join(f'CONFIG_{key}=y\n' for key in builtin)
        config += ''.join(f'CONFIG_{key}=m\n' for key in modular)
        files = {'config-6.18.51-ophub': config.encode()}
        files.update({f'rockchip/{name}': b'dtb fixture' for name in dtbs})
        files.update({f'lib/modules/6.18.51-ophub/{name}.ko': b'module fixture'
                      for name in modular.values() if name != omit_module})
        nested = io.BytesIO()
        with tarfile.open(fileobj=nested, mode='w:gz') as archive:
            for name, content in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        path = self.root / 'kernel.tar.gz'
        with tarfile.open(path, mode='w:gz') as archive:
            info = tarfile.TarInfo('boot-6.18.51-ophub.tar.gz')
            info.size = len(nested.getvalue())
            archive.addfile(info, io.BytesIO(nested.getvalue()))
        return path

    def check(self, archive, *args):
        return subprocess.run([sys.executable, str(ROOT / 'Scripts/Check-DAEDE-Kernel.py'),
                               str(archive), '--fakeflow', *args], capture_output=True, text=True)

    def test_kernel_requires_every_selected_dtb(self):
        panther = 'rk3566-panther-x2.dtb'
        fine = 'rk3399-fine3399.dtb'
        archive = self.archive([panther])
        self.assertEqual(self.check(archive, '--panther-x2').returncode, 0)
        result = self.check(archive, '--dtb', panther, '--dtb', fine)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(fine, result.stderr)
        archive = self.archive([panther, fine])
        self.assertEqual(self.check(archive, '--dtb', panther, '--dtb', fine).returncode, 0)

    def test_kernel_still_rejects_missing_fakeflow_module(self):
        archive = self.archive(['rk3399-fine3399.dtb'], omit_module='tun')
        result = self.check(archive, '--dtb', 'rk3399-fine3399.dtb')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('tun.ko', result.stderr)

    def test_kernel_staging_requires_matching_modules_and_dtbs(self):
        folder = self.root / 'compiled'
        folder.mkdir()
        for prefix in ('boot', 'modules', 'dtb-rockchip'):
            (folder / f'{prefix}-6.18.51-ophub.tar.gz').write_bytes(b'fixture')
        self.assertEqual(stage_kernel.stage(self.root), '6.18.51')
        self.assertTrue((self.root / '6.18.51/dtb-rockchip-6.18.51-ophub.tar.gz').exists())

    def test_builder_ref_matches_lock(self):
        lock = json.loads((COMMON / 'sources.json').read_text())
        workflow = (ROOT / '.github/workflows/ARM64-OPhub-CORE.yml').read_text(encoding='utf-8')
        self.assertIn('uses: ophub/amlogic-s9xxx-armbian@' + lock['kernel']['builder_commit'], workflow)

    def test_fine3399_direct_lan_overlay_removes_only_generated_bridge(self):
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        calls = self.root / 'uci.calls'
        fake_uci = bin_dir / 'uci'
        fake_uci.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = show ]; then\n'
            '  printf "%s\\n" "network.@device[0].name='"'"'br-lan'"'"'" "network.@device[1].name='"'"'other'"'"'"\n'
            '  exit 0\n'
            'fi\n'
            'printf "%s\\n" "$*" >> "$UCI_CALLS"\n',
            encoding='utf-8',
        )
        os.chmod(fake_uci, 0o755)
        environment = os.environ.copy()
        environment['PATH'] = str(bin_dir) + os.pathsep + environment['PATH']
        environment['UCI_CALLS'] = str(calls)
        result = subprocess.run(
            ['/bin/sh', str(COMMON / 'fine3399-direct-lan')],
            env=environment, capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = calls.read_text(encoding='utf-8').splitlines()
        self.assertIn("set network.lan.device=eth0", recorded)
        self.assertIn("-q delete network.@device[0]", recorded)
        self.assertNotIn("-q delete network.@device[1]", recorded)


if __name__ == '__main__':
    unittest.main()
