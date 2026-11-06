#!/usr/bin/env python3
"""Check the AP8220 single-rootfs image contract before publishing."""

import struct
import sys
import tarfile
from pathlib import Path

BOARD = "aliyun_ap8220"
PREFIX = "sysupgrade-" + BOARD + "/"


def fdt_props(blob):
    if len(blob) < 40 or struct.unpack_from(">I", blob)[0] != 0xD00DFEED:
        raise ValueError("not an FDT/FIT image")
    total, off_struct, off_str = struct.unpack_from(">III", blob, 4)
    pos = off_struct
    stack = []
    props = {}
    while pos < total:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:
            end = blob.index(0, pos)
            stack.append(blob[pos:end].decode("latin1"))
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from(">II", blob, pos)
            pos += 8
            end = blob.index(0, off_str + nameoff)
            key = blob[off_str + nameoff:end].decode("latin1")
            val = blob[pos:pos + size]
            pos = (pos + size + 3) & ~3
            props.setdefault("/" + "/".join(stack[1:]), {})[key] = val
        elif token == 4:
            continue
        elif token == 9:
            return props
    raise ValueError("missing FDT_END token")


def check_kernel_dtb(kernel, where):
    if kernel[:4] != b"\xd0\x0d\xfe\xed":
        raise ValueError(where + ": kernel is not a FIT image")
    off = kernel.find(b"\xd0\x0d\xfe\xed", 4)
    if off < 0:
        raise ValueError(where + ": no device tree inside the FIT")
    total = struct.unpack_from(">I", kernel, off + 4)[0]
    dtb = kernel[off:off + total]
    props = fdt_props(dtb)

    nand = None
    for path, node in props.items():
        if path.endswith("nand-controller@79b0000/nand@0") and "nand-ecc-strength" in node:
            nand = node
            break
    if nand is None:
        raise ValueError(where + ": NAND node missing from the device tree")

    ecc = struct.unpack(">I", nand.get("nand-ecc-strength", b""))[0]
    if ecc != 8:
        raise ValueError(where + ": nand-ecc-strength is %d, this NAND needs 8" % ecc)

    part_node = path = None
    for path, node in props.items():
        if path.endswith("nand@0/partitions"):
            part_node = node
            break
    if part_node is None:
        raise ValueError(where + ": NAND partitions node missing")

    compat = part_node.get("compatible", b"").rstrip(b"\x00").decode("latin1")
    if compat != "qcom,smem-part":
        raise ValueError(where + ": NAND partitions use " + repr(compat)
                         + ", expected qcom,smem-part (fixed partitions mean the old dual-partition patch leaked in)")

    for path, node in props.items():
        if path.endswith("nand@0/partitions/partition@0"):
            raise ValueError(where + ": fixed partition present under NAND, MIBIB layout would be bypassed")

    return "ecc=8 step=512 partitions=qcom,smem-part"


def check_sysupgrade(path):
    with tarfile.open(path) as archive:
        names = set(archive.getnames())
        for member in ("CONTROL", "kernel", "root"):
            if PREFIX + member not in names:
                raise ValueError("sysupgrade: missing member " + PREFIX + member)
        control = archive.extractfile(PREFIX + "CONTROL").read()
        if b"BOARD=" + BOARD.encode() not in control:
            raise ValueError("sysupgrade: CONTROL does not name " + BOARD)
        kernel = archive.extractfile(PREFIX + "kernel").read()
        root = archive.extractfile(PREFIX + "root").read()
    if root[:4] != b"hsqs":
        raise ValueError("sysupgrade: root is not a SquashFS image")
    return check_kernel_dtb(kernel, "sysupgrade")


def check_factory_ubi(path):
    head = path.read_bytes()[:4]
    if head != b"UBI#":
        raise ValueError("factory.ubi: missing UBI# magic")
    return "ubi image, " + str(path.stat().st_size) + " bytes"


def main():
    root = Path(sys.argv[1])
    sysupgrades = [p for p in root.glob("*" + BOARD + "*sysupgrade*.bin") if not p.name.endswith(".sha256")]
    factories = [p for p in root.glob("*" + BOARD + "*factory.ubi")]
    if not sysupgrades:
        raise SystemExit("no sysupgrade image found under " + str(root))
    if not factories:
        raise SystemExit("no factory.ubi found under " + str(root) + " (IMAGES must keep Device/UbiFit output)")
    print("sysupgrade:", sysupgrades[0].name, "->", check_sysupgrade(sysupgrades[0]))
    print("factory  :", factories[0].name, "->", check_factory_ubi(factories[0]))
    print("AP8220 single-rootfs contract OK")


if __name__ == "__main__":
    main()
