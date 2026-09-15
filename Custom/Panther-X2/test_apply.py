#!/usr/bin/env python3
"""Exercise the port against real upstream Makefiles without modifying them."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
upstream = Path(sys.argv[1]).resolve()
paths = ['target/linux/rockchip/image/armv8.mk', 'package/boot/uboot-rockchip/Makefile']


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def run(root, success, *args):
    result = subprocess.run([sys.executable, str(HERE/'apply.py'), str(root), *args], capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    return result


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for path in paths:
        dest = root/path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upstream/path, dest)
    run(root, True)
    first = snapshot(root)
    run(root, True)
    assert snapshot(root) == first, 'Repeat application changed files'
    # Stale upstream assets must fail before any integration mutation.
    dts = root/'target/linux/rockchip/files/arch/arm64/boot/dts/rockchip/rk3566-panther-x2.dts'
    dts.write_text('upstream changed this file\n')
    before = snapshot(root)
    run(root, False)
    assert snapshot(root) == before, 'Conflict changed source files'
    # A silently discarded U-Boot selection must stop a build.
    (root/'.config').write_text('CONFIG_TARGET_rockchip=y\n')
    run(root, False, '--verify-config')

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for path in paths:
        dest = root/path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upstream/path, dest)
    path = root/paths[1]
    path.write_text(path.read_text().replace('# RK3568 boards', '# Changed upstream layout'))
    before = snapshot(root)
    run(root, False)
    assert snapshot(root) == before, 'Patch conflict changed source files'

print('PASS: upstream application, idempotence, asset conflict, patch conflict, missing configuration')
