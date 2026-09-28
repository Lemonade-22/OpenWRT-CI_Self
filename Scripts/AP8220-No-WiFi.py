#!/usr/bin/env python3
"""Enforce the AP8220 wired-only profile while preserving LuCI administration."""
import json
import re
import sys
from pathlib import Path


def wireless(name):
    return bool(re.match(
        r'^(?:kmod-(?:ath|ath9k|ath10k|ath11k|ath12k|mac80211|cfg80211)(?:-|$)'
        r'|(?:ath9k|ath10k|ath11k|ath12k|ipq-wifi)(?:-|$)'
        r'|(?:wpad|hostapd|wpa-supplicant)(?:-|$)'
        r'|(?:wifi-scripts|wireless-regdb|iw|iw-full|iwlwifi-firmware)$'
        r'|luci-(?:app|i18n)-(?:dawn|usteer|wifischedule|travelmate|wireless|wifi)(?:-|$))', name))


def prepare():
    # Remove profile defaults as well as Kconfig selections; device packages can
    # otherwise request a module even when it is absent from the global rootfs.
    for filename in ('target/linux/qualcommax/Makefile',
                     'target/linux/qualcommax/image/ipq807x.mk'):
        path = Path(filename)
        text = path.read_text()
        text = re.sub(r'(?<![\w-])(?:kmod-ath11k(?:-ahb|-pci)?|wpad-openssl|ipq-wifi-aliyun_ap8220)(?![\w-])', '', text)
        path.write_text(text)

    luci = Path('feeds/luci/modules')
    menu = luci / 'luci-mod-network/root/usr/share/luci/menu.d/luci-mod-network.json'
    data = json.loads(menu.read_text())
    data.pop('admin/network/wireless', None)
    menu.write_text(json.dumps(data, indent=2) + '\n')
    for relative in (
        'luci-mod-network/htdocs/luci-static/resources/view/network/wireless.js',
        'luci-mod-status/htdocs/luci-static/resources/view/status/include/60_wifi.js',
    ):
        (luci / relative).unlink(missing_ok=True)


def configure():
    path = Path('.config')
    text = path.read_text()
    names = set(re.findall(r'(?:CONFIG_PACKAGE_|config PACKAGE_)([\w+.-]+)', text))
    metadata = Path('tmp/.config-package.in')
    names.update(re.findall(r'config PACKAGE_([\w+.-]+)', metadata.read_text()))
    excluded = sorted(filter(wireless, names))
    lines = [line for line in text.splitlines()
             if not any(line.startswith('CONFIG_PACKAGE_' + name + '=') or
                        line == '# CONFIG_PACKAGE_' + name + ' is not set'
                        for name in excluded)]
    lines += ['# CONFIG_PACKAGE_' + name + ' is not set' for name in excluded]
    path.write_text('\n'.join(lines) + '\n')


def verify_config():
    text = Path('.config').read_text()
    selected = re.findall(r'^CONFIG_PACKAGE_([\w+.-]+)=[ym]$', text, re.M)
    bad = sorted(filter(wireless, selected))
    if bad:
        raise ValueError('Wireless packages still selected: ' + ', '.join(bad))
    for package in ('luci', 'luci-mod-network', 'luci-mod-status'):
        if package not in selected:
            raise ValueError('Required web management package missing: ' + package)
    print('AP8220: no wireless drivers/services selected (y or m); LuCI retained')


def verify_manifest(directory):
    files = list(Path(directory).glob('*.manifest'))
    if not files:
        raise ValueError('No firmware package manifest found')
    for path in files:
        bad = [line.split()[0] for line in path.read_text().splitlines()
               if line.strip() and wireless(line.split()[0])]
        if bad:
            raise ValueError(f'{path}: wireless packages present: {bad}')
    print('AP8220 manifests contain no wireless drivers/services')


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'prepare':
        prepare()
    elif mode == 'configure':
        configure()
    elif mode == 'verify':
        verify_config()
    elif mode == 'manifest':
        verify_manifest(sys.argv[2])
    else:
        raise ValueError(mode)
