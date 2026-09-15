#!/usr/bin/env python3
"""Apply pinned board support; refuse drift before changing the source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--verify-config', action='store_true')
    args = parser.parse_args()
    root = args.source.resolve()
    if args.verify_config:
        config = (root / '.config').read_text()
        required = [
            'CONFIG_TARGET_rockchip=y',
            'CONFIG_TARGET_rockchip_armv8=y',
            'CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_panther_x2=y',
            'CONFIG_PACKAGE_u-boot-panther-x2-rk3566=y',
        ]
        missing = [s for s in required if s not in config.splitlines()]
        if missing:
            raise SystemExit('Panther X2 configuration was dropped: ' + ', '.join(missing))
        print('Panther X2 device and U-Boot selected after make defconfig.')
        return

    manifest = json.loads((HERE / 'sources.json').read_text())
    for name, digest in manifest['sha256'].items():
        asset = (HERE / name).resolve()
        if not asset.is_relative_to(HERE) or hashlib.sha256(asset.read_bytes()).hexdigest() != digest:
            raise SystemExit('Support asset checksum mismatch: ' + name)

    image = root / 'target/linux/rockchip/image/armv8.mk'
    uboot = root / 'package/boot/uboot-rockchip/Makefile'
    image_text = image.read_text()
    uboot_text = uboot.read_text()
    if 'define Device/rk3566\n' not in image_text or 'define U-Boot/rk3566/Default\n' not in uboot_text:
        raise SystemExit('Upstream RK3566 definitions changed; review the port before building.')

    patch = str(HERE / 'integration.patch')
    forward = git(root, 'apply', '--check', patch)
    reverse = git(root, 'apply', '--reverse', '--check', patch)
    stamp = root / '.panther-x2-support.json'
    already_applied = forward.returncode != 0 and reverse.returncode == 0 and stamp.is_file()
    if forward.returncode and not already_applied:
        raise SystemExit('Panther X2 integration conflicts with upstream; no files changed.\n' + forward.stderr)
    if not already_applied and ('define Device/panther_x2\n' in image_text or 'define U-Boot/panther-x2-rk3566\n' in uboot_text):
        raise SystemExit('Upstream already defines Panther X2; review and retire the local port.')

    copies = []
    for asset in sorted((HERE / 'files').rglob('*')):
        if not asset.is_file():
            continue
        relative = asset.relative_to(HERE / 'files')
        dest = root / relative
        if not dest.resolve().is_relative_to(root):
            raise SystemExit('Asset destination escapes the source checkout: ' + str(relative))
        if dest.exists() and dest.read_bytes() != asset.read_bytes():
            raise SystemExit('Existing upstream file differs; no files changed: ' + str(relative))
        copies.append((asset, dest))

    # Detect a second U-Boot patch adding the same defconfig under another name.
    expected = '316-rockchip-rk3566-Add-support-for-panther-x2.patch'
    for candidate in (root / 'package/boot/uboot-rockchip/patches').glob('*.patch'):
        if candidate.name != expected and '+++ b/configs/panther-x2-rk3566_defconfig' in candidate.read_text(errors='replace'):
            raise SystemExit('Another upstream patch adds Panther X2; review: ' + str(candidate))

    if not already_applied:
        result = git(root, 'apply', patch)
        if result.returncode:
            raise SystemExit(result.stderr)
    for asset, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(asset.read_bytes())
    source_commit = git(root, 'rev-parse', 'HEAD')
    record = dict(manifest)
    record['immortalwrt_commit'] = source_commit.stdout.strip() if source_commit.returncode == 0 else 'unavailable'
    stamp.write_text(json.dumps(record, indent=2) + '\n')
    print('Panther X2 support verified/applied. LEDE source: ' + manifest['lede_commit'])


if __name__ == '__main__':
    main()
