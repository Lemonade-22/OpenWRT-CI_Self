#!/usr/bin/env python3
"""Stage the actual compiled kernel release under ophub's version directory."""
import re
import shutil
import sys
from pathlib import Path

def stage(root):
    root = Path(root)
    boots = sorted(root.rglob("boot-*.tar.gz"))
    if len(boots) != 1:
        raise ValueError(f"Expected one boot archive, found {len(boots)}")
    boot = boots[0]
    release = boot.name[len("boot-"):-len(".tar.gz")]
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-[A-Za-z0-9._+-]+)?", release)
    if not match:
        raise ValueError(f"Unsupported kernel release: {release}")
    version = match[1]
    files = [boot, boot.with_name(f"dtb-rockchip-{release}.tar.gz"),
             boot.with_name(f"modules-{release}.tar.gz")]
    for path in files:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing matching kernel archive: {path.name}")
    target = root / version
    target.mkdir(exist_ok=True)
    for path in files:
        dest = target / path.name
        if path.resolve() != dest.resolve():
            if dest.exists():
                raise ValueError(f"Refusing to overwrite kernel archive: {dest}")
            shutil.copy2(path, dest)
    return version

if __name__ == "__main__":
    try:
        print(stage(sys.argv[1]))
    except (ValueError, OSError) as error:
        sys.exit(f"::error::{error}")
