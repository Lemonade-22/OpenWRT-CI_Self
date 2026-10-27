"""Exercise the Fine3399 first-boot network overlay without touching a device.

The overlay is a uci-defaults script staged by the workflow only for the
fine3399 board. eth0 is the native RTL8211F GMAC (LAN) and eth1 is the
RTL8153 USB NIC (WAN). A fake ``uci`` records every configuration call.
"""

import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'Custom/ARM64-OPhub/fine3399-direct-lan'
WORKFLOW = ROOT / '.github/workflows/ARM64-OPhub-CORE.yml'
BOARD_CONDITION = 'if [ "$BOARD" = fine3399 ]; then'


class Fine3399NetworkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='test-fine3399-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        self.calls_file = self.root / 'uci.calls'
        fake_uci = bin_dir / 'uci'
        fake_uci.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = show ]; then\n'
            "  printf '%s\\n' \"network.@device[0].name='br-lan'\" \"network.@device[1].name='other'\"\n"
            '  exit 0\n'
            'fi\n'
            'printf "%s\\n" "$*" >> "$UCI_CALLS"\n',
            encoding='utf-8', newline='\n',
        )
        os.chmod(fake_uci, 0o755)
        self.environment = os.environ.copy()
        self.environment['PATH'] = str(bin_dir) + os.pathsep + self.environment['PATH']
        self.environment['UCI_CALLS'] = str(self.calls_file)

    def run_overlay(self):
        return subprocess.run(
            ['/bin/sh', str(OVERLAY)], env=self.environment,
            capture_output=True, text=True, encoding='utf-8',
        )

    def calls(self):
        return self.calls_file.read_text(encoding='utf-8').splitlines()

    def overlay_text(self):
        return OVERLAY.read_text(encoding='utf-8')

    def test_lan_is_static_on_the_native_gmac(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.calls()
        self.assertIn('-q delete network.lan.ifname', recorded)
        self.assertIn('set network.lan.device=eth0', recorded)
        self.assertIn('set network.lan.proto=static', recorded)
        self.assertIn('set network.lan.ipaddr=192.168.10.1', recorded)
        self.assertIn('set network.lan.netmask=255.255.255.0', recorded)
        for call in recorded:
            self.assertNotIn('set network.lan.ifname=', call)

    def test_only_the_generated_br_lan_device_is_deleted(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.calls()
        self.assertIn('-q delete network.@device[0]', recorded)
        self.assertNotIn('-q delete network.@device[1]', recorded)
        self.assertNotIn('-q delete network.@device[2]', recorded)

    def test_wan_is_configured_before_the_usb_nic_enumerates(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.calls()
        self.assertIn('set network.wan=interface', recorded)
        self.assertIn('set network.wan.device=eth1', recorded)
        self.assertIn('set network.wan.proto=dhcp', recorded)
        self.assertIn('set network.wan.ipv6=1', recorded)
        self.assertIn('set network.wan6=interface', recorded)
        self.assertIn('set network.wan6.device=@wan', recorded)
        self.assertIn('set network.wan6.proto=dhcpv6', recorded)
        self.assertIn('-q delete network.wan.ifname', recorded)
        for call in recorded:
            self.assertNotIn('set network.wan.ifname=', call)
            self.assertNotIn('set network.wan6.device=eth1', call)

    def test_dhcp_server_is_explicit_for_the_lan_interface(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.calls()
        self.assertIn('set dhcp.lan=dhcp', recorded)
        self.assertIn('set dhcp.lan.interface=lan', recorded)
        self.assertIn('-q delete dhcp.lan.ignore', recorded)
        self.assertIn('set dhcp.lan.start=100', recorded)
        self.assertIn('set dhcp.lan.limit=150', recorded)
        self.assertIn('set dhcp.lan.leasetime=12h', recorded)
        self.assertIn('set dhcp.lan.dhcpv6=server', recorded)
        self.assertIn('set dhcp.lan.ra=server', recorded)
        for call in recorded:
            self.assertNotIn('ignore=1', call)

    def test_network_and_dhcp_are_committed_after_configuration(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self.calls()
        network_sets = [i for i, call in enumerate(recorded) if call.startswith('set network.')]
        dhcp_sets = [i for i, call in enumerate(recorded) if call.startswith('set dhcp.')]
        self.assertTrue(network_sets)
        self.assertTrue(dhcp_sets)
        self.assertLess(max(network_sets), recorded.index('commit network'))
        self.assertLess(max(dhcp_sets), recorded.index('commit dhcp'))

    def test_overlay_is_posix_sh_without_runtime_workarounds(self):
        result = self.run_overlay()
        self.assertEqual(result.returncode, 0, result.stderr)
        syntax = subprocess.run(['/bin/sh', '-n', str(OVERLAY)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        text = self.overlay_text()
        # Check executable lines only: comments are free to explain why this is
        # a uci-defaults script and why no runtime workaround is needed.
        code = '\n'.join(
            line for line in text.splitlines() if not line.lstrip().startswith('#'))
        self.assertIsNone(re.search(r'(?m)^\s*\[\[', code))
        self.assertNotIn('/etc/', code)
        self.assertNotIn('hotplug', code.lower())
        self.assertNotIn('sleep', code.lower())
        self.assertNotIn('rc.local', code)
        self.assertNotIn('procd', code)
        self.assertNotIn('/sys/class/net', code)
        self.assertNotIn('ip link', code)
        self.assertIsNone(re.search(r'(?m)^\s*(if|while|until)\b', code),
                          'the overlay must not probe for eth1 or poll at runtime')

    def test_workflow_stages_the_overlay_only_for_the_fine3399_board(self):
        workflow = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn(BOARD_CONDITION, workflow)
        lines = workflow.splitlines()
        start = next(index for index, line in enumerate(lines) if BOARD_CONDITION in line)
        end = start
        while end < len(lines) and lines[end].strip() != 'fi':
            end += 1
        self.assertLess(end, len(lines))
        block = '\n'.join(lines[start:end + 1])
        self.assertIn('install -m 0755', block)
        self.assertIn('Custom/ARM64-OPhub/fine3399-direct-lan', block)
        self.assertIn('etc/uci-defaults/99-fine3399-direct-lan', block)
        for index, line in enumerate(lines):
            if 'fine3399-direct-lan' in line:
                self.assertGreaterEqual(index, start)
                self.assertLessEqual(index, end)

    def test_authored_files_use_lf_line_endings(self):
        for path in (OVERLAY, Path(__file__).resolve()):
            data = path.read_bytes()
            self.assertNotIn(b'\r', data, f'{path} must use LF line endings')


if __name__ == '__main__':
    unittest.main()
