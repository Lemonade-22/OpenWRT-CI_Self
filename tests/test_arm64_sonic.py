"""Exercise the SONiC kernel config, archive gates and pinned source preparation offline."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import signal
import sys
import tarfile
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover - only structural checks need PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'Custom/ARM64-OPhub'
GATE = ROOT / 'Scripts/Check-DAEDE-Kernel.py'
WORKFLOW = ROOT / '.github/workflows/ARM64-OPhub-CORE.yml'
ACTION = ROOT / '.github/actions/arm64-ophub-validate/action.yml'


def load(name):
    spec = importlib.util.spec_from_file_location(name, COMMON / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_kernel = load('prepare_kernel')
prepare_kernel_source = load('prepare_kernel_source')

BASE_BUILTIN = ('BPF BPF_SYSCALL BPF_JIT CGROUPS CGROUP_BPF KPROBES KPROBE_EVENTS '
                'BPF_EVENTS DEBUG_INFO_BTF BPF_STREAM_PARSER XDP_SOCKETS NET_CLS_ACT '
                'NET_INGRESS NET_EGRESS NET_NS COMPAT SYSVIPC NAMESPACES IPC_NS PACKET TMPFS BINFMT_ELF').split()
BASE_MODULES = {'NET_SCH_INGRESS': 'sch_ingress', 'NET_CLS_BPF': 'cls_bpf',
                'NET_ACT_BPF': 'act_bpf', 'VETH': 'veth', 'DUMMY': 'dummy', 'TUN': 'tun'}
SONIC_CONFIG = {
    'NF_NAT_FULLCONE': 'y', 'NF_CT_PROTO_UDPLITE': 'y', 'NF_CT_PROTO_SCTP': 'y',
    'NF_NAT': 'm', 'NF_NAT_MASQUERADE': 'y', 'NF_TABLES': 'm', 'NFT_NAT': 'm',
    'NFT_MASQ': 'm', 'NETFILTER_XT_TARGET_MASQUERADE': 'm', 'NETFILTER_XT_NAT': 'm',
}
SONIC_MODULES = {'NF_TABLES': 'nf_tables', 'NFT_NAT': 'nft_nat', 'NF_NAT': 'nf_nat', 'NFT_MASQ': 'nft_masq',
                 'NETFILTER_XT_TARGET_MASQUERADE': 'xt_MASQUERADE'}
DEVICE_CONFIG = {
    'STMMAC_ETH': 'y', 'STMMAC_PLATFORM': 'y', 'DWMAC_ROCKCHIP': 'y',
    'DWMAC_GENERIC': 'y', 'REALTEK_PHY': 'y', 'USB_RTL8152': 'm',
    'BRIDGE': 'y', 'BRIDGE_VLAN_FILTERING': 'y', 'VLAN_8021Q': 'm',
}
DEVICE_MODULES = {'STMMAC_ETH': 'stmmac', 'DWMAC_ROCKCHIP': 'dwmac_rockchip',
                  'REALTEK_PHY': 'realtek', 'USB_RTL8152': 'r8152'}
SONIC_MARKER_FILES = (
    ('include/uapi/linux/netfilter/nf_nat.h', 'NF_NAT_RANGE_FULLCONE'),
    ('net/netfilter/xt_MASQUERADE.c', '"FULLCONE"'),
    ('net/netfilter/nft_masq.c', 'nft_fullcone_type'),
)


def git(path, *arguments, check=True):
    result = subprocess.run(['git', '-C', str(path), *arguments], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f'git {" ".join(arguments)} failed: {result.stderr}')
    return result


def init_git_repository(path, files):
    """Create a tiny committed git fixture and return its HEAD commit."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    git(path, 'config', 'user.email', 'fixture@example.com')
    git(path, 'config', 'user.name', 'Fixture')
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='\n')
    git(path, 'add', '-A')
    git(path, 'commit', '-q', '-m', 'fixture')
    return git(path, 'rev-parse', 'HEAD').stdout.strip()


def make_patch(repository, relative, modified):
    """Return a unified diff for changing relative in repository to modified."""
    repository = Path(repository)
    target = repository / relative
    original = target.read_text(encoding='utf-8')
    target.write_text(modified, encoding='utf-8', newline='\n')
    patch = git(repository, 'diff', '--', relative).stdout
    target.write_text(original, encoding='utf-8', newline='\n')
    git(repository, 'checkout', '--', relative)
    return patch


class SonicKernelGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def archive(self, overrides=None, omit=(), omit_modules=(), extra_modules=(), dtbs=()):
        config = {}
        config.update({key: 'y' for key in BASE_BUILTIN})
        config.update({key: 'm' for key in BASE_MODULES})
        config.update(SONIC_CONFIG)
        config.update(DEVICE_CONFIG)
        config.update(overrides or {})
        for key in omit:
            config.pop(key, None)
        lines = ''.join(f'CONFIG_{key}={value}\n' for key, value in config.items())
        files = {'config-6.18.59-ophub': lines}
        modules = {}
        modules.update(BASE_MODULES)
        modules.update(SONIC_MODULES)
        modules.update(DEVICE_MODULES)
        names = {module for symbol, module in modules.items() if config.get(symbol) == 'm'}
        if config.get('NFT_NAT') == 'm':
            names.add('nft_chain_nat')
        names.update(extra_modules)
        names -= set(omit_modules)
        for module in names:
            files[f'lib/modules/6.18.59-ophub/{module}.ko'] = 'module fixture'
        for dtb in dtbs:
            files[f'rockchip/{dtb}'] = 'dtb fixture'
        path = self.root / 'kernel.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, content in files.items():
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return path

    def check(self, archive, *arguments):
        return subprocess.run([sys.executable, str(GATE), str(archive), *arguments],
                              capture_output=True, text=True)

    def test_sonic_fine3399_archive_passes(self):
        archive = self.archive(dtbs=('rk3399-fine3399.dtb',))
        result = self.check(archive, '--fakeflow', '--sonic',
                            '--device', 'fine3399', '--dtb', 'rk3399-fine3399.dtb')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SONiC fullcone', result.stdout)
        self.assertIn('Fine3399', result.stdout)

    def test_sonic_gate_is_opt_in(self):
        archive = self.archive(omit=tuple(SONIC_CONFIG))
        self.assertEqual(self.check(archive, '--fakeflow').returncode, 0)

    def test_sonic_gate_rejects_missing_fullcone_core_symbol(self):
        archive = self.archive(omit=('NF_NAT_FULLCONE',))
        result = self.check(archive, '--fakeflow', '--sonic')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('NF_NAT_FULLCONE=y', result.stderr)

    def test_sonic_gate_rejects_missing_udplite_and_sctp(self):
        for symbol in ('NF_CT_PROTO_UDPLITE', 'NF_CT_PROTO_SCTP'):
            archive = self.archive(omit=(symbol,))
            result = self.check(archive, '--fakeflow', '--sonic')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(symbol, result.stderr)

    def test_sonic_gate_rejects_missing_modular_nft_masq(self):
        archive = self.archive(omit_modules=('nft_masq',))
        result = self.check(archive, '--fakeflow', '--sonic')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nft_masq.ko', result.stderr)

    def test_sonic_gate_rejects_missing_nat_or_tables_modules(self):
        for module in ('nft_nat', 'nft_chain_nat', 'nf_tables'):
            with self.subTest(module=module):
                result = self.check(self.archive(omit_modules=(module,)), '--sonic')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(module + '.ko', result.stderr)

    def test_sonic_gate_rejects_legacy_fullcone_config_symbol(self):
        for symbol in ('NFT_FULLCONE', 'NETFILTER_XT_TARGET_FULLCONENAT'):
            archive = self.archive(overrides={symbol: 'm'})
            result = self.check(archive, '--fakeflow', '--sonic')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f'CONFIG_{symbol}', result.stderr)
            self.assertIn('legacy fullcone config', result.stderr)

    def test_sonic_gate_rejects_legacy_fullcone_module_file(self):
        archive = self.archive(extra_modules=('nft_fullcone',))
        result = self.check(archive, '--fakeflow', '--sonic')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nft_fullcone.ko', result.stderr)

    def test_fine3399_gate_requires_r8152_module(self):
        archive = self.archive(omit_modules=('r8152',), dtbs=('rk3399-fine3399.dtb',))
        result = self.check(archive, '--fakeflow', '--sonic', '--device', 'fine3399')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('r8152.ko', result.stderr)
        self.assertEqual(self.check(archive, '--fakeflow', '--sonic').returncode, 0)

    def test_fine3399_gate_requires_stmmac_driver(self):
        archive = self.archive(omit=('STMMAC_ETH',))
        result = self.check(archive, '--fakeflow', '--sonic', '--device', 'fine3399')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STMMAC_ETH', result.stderr)

    def test_panther_x2_needs_no_extra_kernel_symbols(self):
        archive = self.archive(omit=tuple(DEVICE_CONFIG), dtbs=('rk3566-panther-x2.dtb',))
        result = self.check(archive, '--fakeflow', '--sonic', '--device', 'panther-x2',
                            '--panther-x2')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_device_is_rejected(self):
        result = self.check(self.archive(), '--device', 'unknown-board')
        self.assertNotEqual(result.returncode, 0)


class PrepareKernelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.prerequisites = ''.join(
            f'CONFIG_{symbol}={allowed[0]}\n'
            for symbol, allowed in prepare_kernel.PREREQUISITES.items()
        )

    def make_kernel_fork(self, config_text):
        fork = self.root / 'kernel-fork'
        relative = Path('kernel-config/release/stable/config-6.18')
        head = init_git_repository(fork, {str(relative): config_text})
        return fork / relative, {
            'version': '6.18.59',
            'config_commit': head,
            'config_path': 'kernel-config/release/stable',
        }

    def test_module_tables_contain_sonic_and_device_requirements(self):
        expected_sonic = {
            'NF_NAT_FULLCONE': 'y', 'NF_CT_PROTO_UDPLITE': 'y', 'NF_CT_PROTO_SCTP': 'y',
            'NF_NAT': 'm', 'NF_NAT_MASQUERADE': 'y', 'NF_TABLES': 'm', 'NFT_NAT': 'm',
            'NFT_MASQ': 'm', 'NETFILTER_XT_TARGET_MASQUERADE': 'm',
            'NETFILTER_XT_NAT': 'm',
        }
        for symbol, value in expected_sonic.items():
            self.assertEqual(prepare_kernel.SONIC.get(symbol), value)
        expected_device = {
            'STMMAC_ETH': 'y', 'STMMAC_PLATFORM': 'y', 'DWMAC_ROCKCHIP': 'y',
            'DWMAC_GENERIC': 'y', 'REALTEK_PHY': 'y', 'USB_RTL8152': 'm',
            'BRIDGE': 'y', 'BRIDGE_VLAN_FILTERING': 'y', 'VLAN_8021Q': 'm',
        }
        for symbol, value in expected_device.items():
            self.assertEqual(prepare_kernel.DEVICE.get(symbol), value)
        for symbol in ('ARCH_ROCKCHIP', 'OF', 'USB', 'USB_SUPPORT', 'PHYLIB', 'MII',
                       'NETFILTER_ADVANCED', 'NF_CONNTRACK'):
            self.assertIn(symbol, prepare_kernel.PREREQUISITES)

    def test_prepare_writes_sonic_and_device_symbols(self):
        existing = ('CONFIG_ARCH_ROCKCHIP=y\n# CONFIG_DEBUG_INFO is not set\n'
                    'CONFIG_NFT_FULLCONE=m\nCONFIG_NETFILTER_XT_TARGET_FULLCONENAT=m\n')
        config, lock = self.make_kernel_fork(self.prerequisites + existing)
        prepare_kernel.prepare(self.root, lock)
        text = config.read_text(encoding='utf-8')
        self.assertNotIn('\r', text)
        values = prepare_kernel.config_values(text)
        for symbol in prepare_kernel.ARM64:
            self.assertEqual(values.get(symbol), 'y', symbol)
        for symbol, value in {**SONIC_CONFIG, **DEVICE_CONFIG}.items():
            self.assertEqual(values.get(symbol), value, symbol)
        for symbol in SONIC_CONFIG:
            self.assertEqual(len(re.findall(rf'^CONFIG_{symbol}=', text, re.M)), 1, symbol)
        self.assertNotIn('CONFIG_NFT_FULLCONE', text)
        self.assertNotIn('CONFIG_NETFILTER_XT_TARGET_FULLCONENAT', text)

    def test_prepare_fails_on_missing_prerequisite(self):
        config, lock = self.make_kernel_fork(self.prerequisites.replace('CONFIG_MII=y\n', ''))
        original = config.read_text(encoding='utf-8')
        with self.assertRaises(SystemExit) as caught:
            prepare_kernel.prepare(self.root, lock)
        self.assertIn('CONFIG_MII', str(caught.exception))
        self.assertEqual(config.read_text(encoding='utf-8'), original)

    def test_prepare_accepts_modular_netfilter_conntrack(self):
        text = self.prerequisites.replace('CONFIG_NF_CONNTRACK=y', 'CONFIG_NF_CONNTRACK=m')
        config, lock = self.make_kernel_fork(text)
        prepare_kernel.prepare(self.root, lock)
        values = prepare_kernel.config_values(config.read_text(encoding='utf-8'))
        self.assertEqual(values.get('NF_NAT_FULLCONE'), 'y')

    def test_prepare_rejects_wrong_config_checkout(self):
        config, lock = self.make_kernel_fork(self.prerequisites)
        lock['config_commit'] = '0' * 40
        with self.assertRaises(AssertionError):
            prepare_kernel.prepare(self.root, lock)


class PrepareKernelSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def make_fixture(self):
        source = self.root / 'kernel-source'
        base = {f'{relative}': f'/* base {index} */\n'
                for index, (relative, _) in enumerate(SONIC_MARKER_FILES)}
        source_head = init_git_repository(source, base)
        patches = {}
        for index, (relative, marker) in enumerate(SONIC_MARKER_FILES):
            patches[f'target/linux/generic/hack-6.18/{984 + index}-fixture.patch'] = make_patch(
                source, relative, base[relative] + marker + '\n' + (
                    (ROOT / 'tests/fixtures/sonic-fullcone-init.c').read_text()
                    if relative.endswith('nft_masq.c') else ''))
        patch_root = self.root / 'patch-checkout'
        patch_head = init_git_repository(patch_root, patches)
        lock = {
            'userspace': {'commit': patch_head, 'kernel_patches': list(patches)},
            'kernel': {
                'source_repository': 'https://example.invalid/linux-6.18.y',
                'source_commit': source_head,
            },
        }
        return patch_root, source, lock, base

    def test_applies_patches_writes_record_and_is_idempotent(self):
        patch_root, source, lock, _ = self.make_fixture()
        record_path = self.root / 'kernel-output/source-preparation.json'
        result = prepare_kernel_source.prepare(patch_root, source, lock=lock, record=record_path)
        self.assertTrue(all(prepare_kernel_source.marker_state(source)))
        record = json.loads(record_path.read_text(encoding='utf-8'))
        self.assertEqual(record['source_repository'], lock['kernel']['source_repository'])
        self.assertEqual(record['source_commit'], lock['kernel']['source_commit'])
        self.assertEqual(record['userspace_commit'], lock['userspace']['commit'])
        self.assertTrue(record['applied'])
        self.assertEqual([item['path'] for item in record['patches']],
                         lock['userspace']['kernel_patches'])
        for item in record['patches']:
            digest = hashlib.sha256((patch_root / item['path']).read_bytes()).hexdigest()
            self.assertEqual(item['sha256'], digest)
        self.assertIsInstance(record['diff_stat'], list)
        self.assertTrue(record['diff_stat'])
        self.assertEqual(len(record['diff_sha256']), 64)
        self.assertNotIn('\r', record_path.read_text(encoding='utf-8'))
        self.assertEqual(result['diff_sha256'], record['diff_sha256'])
        again = prepare_kernel_source.prepare(patch_root, source, lock=lock)
        self.assertTrue(again['applied'])

    def test_accepts_relative_patch_root(self):
        patch_root, source, lock, _ = self.make_fixture()
        relative = Path(os.path.relpath(patch_root, Path.cwd()))
        prepare_kernel_source.prepare(relative, source, lock=lock)
        self.assertTrue(all(prepare_kernel_source.marker_state(source)))

    def test_rejects_partially_patched_source(self):
        patch_root, source, lock, base = self.make_fixture()
        relative, marker = SONIC_MARKER_FILES[0]
        target = source / relative
        target.write_text(base[relative] + marker + '\n', encoding='utf-8', newline='\n')
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError,
                                    'partially patched'):
            prepare_kernel_source.prepare(patch_root, source, lock=lock)

    def test_rejects_wrong_patch_root_commit(self):
        patch_root, source, lock, _ = self.make_fixture()
        lock['userspace']['commit'] = '1' * 40
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError, 'patch root'):
            prepare_kernel_source.prepare(patch_root, source, lock=lock)

    def test_rejects_wrong_destination_commit(self):
        patch_root, source, lock, _ = self.make_fixture()
        lock['kernel']['source_commit'] = '2' * 40
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError, 'Kernel source'):
            prepare_kernel_source.prepare(patch_root, source, lock=lock)

    def test_rejects_missing_patch_file(self):
        patch_root, source, lock, _ = self.make_fixture()
        lock['userspace']['kernel_patches'].append('target/linux/generic/hack-6.18/999-missing.patch')
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError, 'missing'):
            prepare_kernel_source.prepare(patch_root, source, lock=lock)

    def test_check_mode_validates_without_modifying(self):
        patch_root, source, lock, base = self.make_fixture()
        self.assertIsNone(prepare_kernel_source.prepare(patch_root, source, lock=lock, check=True))
        self.assertFalse(any(prepare_kernel_source.marker_state(source)))
        for relative, content in base.items():
            self.assertEqual((source / relative).read_text(encoding='utf-8'), content)

    def test_check_mode_requires_existing_destination(self):
        patch_root, _, lock, _ = self.make_fixture()
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError,
                                    '--check requires an existing'):
            prepare_kernel_source.prepare(patch_root, self.root / 'absent', lock=lock, check=True)

    def test_rejects_non_git_patch_root(self):
        _, source, lock, _ = self.make_fixture()
        plain = self.root / 'plain'
        plain.mkdir()
        with self.assertRaisesRegex(prepare_kernel_source.SourcePreparationError, 'git checkout'):
            prepare_kernel_source.prepare(plain, source, lock=lock)


class FullconeAttributeRegressionTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('cc'),
                         'Linux C compiler required for guard-page regression')
    def test_original_faults_and_translation_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'net/netfilter/nft_masq.c'
            target.parent.mkdir(parents=True)
            target.write_text((ROOT / 'tests/fixtures/sonic-fullcone-init.c').read_text())
            harness = (ROOT / 'tests/fixtures/fullcone-attributes-harness.c').read_text()

            def run_init():
                content = target.read_text()
                start = content.index('static int nft_fullcone_init(')
                end = content.index('static int nft_fullcone_validate(')
                source = root / 'regression.c'
                source.write_text(harness.replace('/* INSERT_KERNEL_INIT */', content[start:end]))
                executable = root / 'regression'
                subprocess.run(['cc', '-O0', '-Wall', '-Wextra', '-Werror',
                                str(source), '-o', str(executable)], check=True)
                return subprocess.run([str(executable)], capture_output=True).returncode

            self.assertEqual(run_init(), -signal.SIGSEGV)
            prepare_kernel_source.apply_ophub_compatibility(root)
            self.assertEqual(run_init(), 0)
            fixed = target.read_bytes()
            prepare_kernel_source.apply_ophub_compatibility(root)
            self.assertEqual(target.read_bytes(), fixed)
            prepare_kernel_source.apply_ophub_compatibility(root, check=True)


class LockAndWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((COMMON / 'sources.json').read_text(encoding='utf-8'))
        cls.workflow_text = WORKFLOW.read_text(encoding='utf-8')
        cls.action_text = ACTION.read_text(encoding='utf-8')

    def test_sources_lock_pins_kernel_and_sonic_patches(self):
        kernel = self.lock['kernel']
        userspace = self.lock['userspace']
        self.assertEqual(kernel['version'], '6.18.59')
        self.assertEqual(kernel['source_repository'], 'https://github.com/ophub/linux-6.18.y')
        self.assertEqual(kernel['source_commit'], 'a0592d712c819c3571d19ad15ec2d55bd8733a02')
        self.assertEqual(userspace['commit'], 'de149751183f3c10cff427b7efb1ed5cbcb4b761')
        patches = userspace['kernel_patches']
        self.assertEqual([path.rsplit('/', 1)[-1] for path in patches],
                         ['984-add-sonic-fullcone-support.patch',
                          '985-add-sonic-fullcone-to-ipt.patch',
                          '986-add-sonic-fullcone-to-nft.patch'])
        self.assertEqual(userspace['sonic_package_config'],
                         'CONFIG_PACKAGE_fullconenat-sonic=y')

    def test_workflow_has_two_sonic_gate_calls_and_expected_invocations(self):
        self.assertEqual(self.workflow_text.count('--sonic'), 2)
        self.assertIn('args=(--fakeflow --sonic)', self.workflow_text)
        self.assertIn('args+=(--device fine3399)', self.workflow_text)
        self.assertIn('python3 Scripts/Check-DAEDE-Kernel.py "$archive" "${args[@]}"',
                      self.workflow_text)
        self.assertIn('args+=(--dtb "$dtb")', self.workflow_text)
        self.assertIn('python3 Scripts/Check-DAEDE-Kernel.py kernel.tar.gz --dtb "$BOARD_DTB" '
                      '--fakeflow --sonic --device "$BOARD"', self.workflow_text)
        self.assertIn('python3 Custom/ARM64-OPhub/prepare_kernel_source.py', self.workflow_text)
        self.assertIn('--patch-root sonic-patches', self.workflow_text)
        self.assertIn('--destination /mnt/arm64-ophub-kernel/compile-kernel/kernel/linux-6.18.y',
                      self.workflow_text)
        self.assertIn('--record kernel-output/source-preparation.json', self.workflow_text)

    def test_workflow_clones_userspace_at_locked_commit(self):
        self.assertIn('repository: VIKINGYFY/immortalwrt', self.workflow_text)
        self.assertIn('ref: ${{ steps.settings.outputs.userspace_commit }}', self.workflow_text)
        self.assertIn('commit=$(jq -er \'.userspace.commit\' "$lock")', self.workflow_text)
        self.assertIn('git -C wrt fetch --quiet --depth=1 origin "$commit"', self.workflow_text)
        self.assertIn('git -C wrt checkout --quiet --detach FETCH_HEAD', self.workflow_text)
        self.assertIn('[[ "$actual" == "$commit" ]]', self.workflow_text)
        userspace_checkout = re.search(
            r'repository: VIKINGYFY/immortalwrt\s*\n\s*ref: ([^\n]+)', self.workflow_text)
        self.assertIsNotNone(userspace_checkout)
        self.assertNotIn('main', userspace_checkout.group(1))

    def test_workflow_verify_packages_uses_kernel_package_definitions(self):
        self.assertIn('verify_packages.py', self.workflow_text)
        self.assertIn('--definitions tmp/.config-package.in', self.workflow_text)

    def test_workflow_env_matches_locked_userspace(self):
        userspace = self.lock['userspace']
        self.assertIn('SOURCE_REPO: ' + userspace['repository'].removeprefix('https://github.com/'),
                      self.workflow_text)
        self.assertIn('SOURCE_BRANCH: ' + userspace['branch'], self.workflow_text)

    @unittest.skipIf(yaml is None, 'PyYAML is not available')
    def test_workflow_parses_and_has_kernel_source_step(self):
        document = yaml.safe_load(self.workflow_text)
        self.assertIn('jobs', document)
        self.assertIn('kernel', document['jobs'])
        steps = document['jobs']['kernel']['steps']
        uses = [step.get('uses', '') for step in steps]
        self.assertTrue(any(use.startswith('actions/checkout@') for use in uses))
        names = [step.get('name', '') for step in steps]
        self.assertIn('Prepare pinned kernel source and apply SONiC patches', names)
        prepare_step = steps[names.index('Prepare pinned kernel source and apply SONiC patches')]
        self.assertIn('prepare_kernel_source.py', prepare_step['run'])
        self.assertIn('--patch-root sonic-patches', prepare_step['run'])

    @unittest.skipIf(yaml is None, 'PyYAML is not available')
    def test_validate_action_checks_sonic_integration(self):
        document = yaml.safe_load(self.action_text)
        self.assertEqual(document['runs']['using'], 'composite')
        text = json.dumps(document)
        self.assertIn('SONIC_SOURCE', text)
        self.assertIn('prepare_kernel_source.py', text)
        self.assertIn('verify_packages.py', text)
        self.assertIn('test_arm64_*.py', text)
        checkouts = [step for step in document['runs']['steps']
                     if str(step.get('uses', '')).startswith('actions/checkout')]
        sonic = [step for step in checkouts
                 if str(step.get('with', {}).get('repository', '')).lower()
                 == 'vikingyfy/immortalwrt']
        self.assertTrue(sonic)
        for step in sonic:
            self.assertIn('userspace_commit', str(step['with'].get('ref')))
            self.assertNotEqual(step['with'].get('ref'), 'main')

    @unittest.skipUnless(os.environ.get('SONIC_SOURCE'), 'SONIC_SOURCE is not provided')
    def test_pinned_sonic_source_checkout(self):
        source = Path(os.environ['SONIC_SOURCE'])
        head = git(source, 'rev-parse', 'HEAD').stdout.strip()
        self.assertEqual(head, self.lock['userspace']['commit'])
        for relative in self.lock['userspace']['kernel_patches']:
            self.assertTrue((source / relative).is_file(), relative)
        makefile = source / 'package/network/utils/fullconenat-sonic/Makefile'
        if makefile.is_file():
            makefile_text = makefile.read_text(encoding='utf-8')
        else:
            # A local sparse reference checkout may omit the package directory;
            # the CI checkout includes it. Fall back to the pinned git object.
            makefile_text = git(
                source, 'show',
                'HEAD:package/network/utils/fullconenat-sonic/Makefile').stdout
        match = re.search(r'^\s*KCONFIG:=(.*)$', makefile_text, re.M)
        self.assertIsNotNone(match)
        for symbol in ('CONFIG_NF_NAT_FULLCONE=y', 'CONFIG_NF_CT_PROTO_UDPLITE=y',
                       'CONFIG_NF_CT_PROTO_SCTP=y'):
            self.assertIn(symbol, match.group(1))
        # Legacy packages conflict with the SONiC replacements and must stay out.
        self.assertIn('kmod-nft-fullcone', makefile_text)
        self.assertIn('ip6tables-mod-fullconenat', makefile_text)

    @unittest.skipUnless(os.environ.get('SONIC_SOURCE'), 'SONIC_SOURCE is not provided')
    def test_pinned_userspace_fw4_nft_integration(self):
        source = Path(os.environ['SONIC_SOURCE'])

        def text(relative):
            path = source / relative
            if path.is_file():
                return path.read_text(encoding='utf-8')
            return git(source, 'show', 'HEAD:' + relative).stdout

        # nftables/fw4/iptables userspace patches must be present at the pin.
        patches = {
            'package/network/config/firewall4/patches/001-sonic-fullcone.patch':
                ('fullcone', 'nft_try_fullcone'),
            'package/network/config/firewall/patches/001-sonic-fullcone.patch':
                ('fullcone',),
            'package/network/utils/nftables/patches/002-nftables-add-fullcone-expression-support.patch':
                ('FULLCONE', 'nft_fullcone'),
            'package/libs/libnftnl/patches/001-libnftnl-add-fullcone-expression-support.patch':
                ('FULLCONE',),
            'package/network/utils/iptables/patches/901-sonic-fullcone.patch':
                ('FULLCONE',),
        }
        for relative, markers in patches.items():
            content = text(relative)
            for marker in markers:
                self.assertIn(marker, content, relative)

    @unittest.skipUnless(os.environ.get('SONIC_SOURCE'), 'SONIC_SOURCE is not provided')
    def test_pinned_userspace_autoloads_sonic_modules(self):
        """The OpenWrt kmod packages must autoload the modules the gate requires."""
        source = Path(os.environ['SONIC_SOURCE'])

        def text(relative):
            path = source / relative
            if path.is_file():
                return path.read_text(encoding='utf-8')
            return git(source, 'show', 'HEAD:' + relative).stdout

        netfilter = text('include/netfilter.mk')
        self.assertIn('(P_XT)nft_masq', netfilter)
        self.assertIn('(P_XT)xt_MASQUERADE', netfilter)
        nft_nat = text('package/kernel/linux/modules/netfilter.mk')
        # kmod-nft-nat and kmod-ipt-nat declare AutoProbe from their module lists,
        # which include nft_masq and xt_MASQUERADE in the pinned userspace.
        self.assertRegex(nft_nat, r'KernelPackage/nft-nat')
        self.assertRegex(nft_nat, r'AutoProbe,\$\(notdir \$\(NFT_NAT-m\)\)')
        self.assertRegex(nft_nat, r'AutoProbe,\$\(notdir \$\(IPT_NAT-m\)\)')


if __name__ == '__main__':
    unittest.main()
