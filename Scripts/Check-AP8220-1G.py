#!/usr/bin/env python3
"""Check the AP8220 1 GiB sysupgrade contract before publishing an image."""

import struct
import sys
import tarfile
from pathlib import Path


def fdt_properties(blob):
    if len(blob) < 40 or struct.unpack_from(">I", blob)[0] != 0xD00DFEED:
        raise ValueError("not an FDT/FIT image")
    total, struct_off, strings_off = struct.unpack_from(">III", blob, 4)
    if total > len(blob):
        raise ValueError("truncated FDT/FIT image")
    pos = struct_off
    stack = []
    while pos < total:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            end = blob.index(0, pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif token == 2:  # FDT_END_NODE
            stack.pop()
        elif token == 3:  # FDT_PROP
            size, offset = struct.unpack_from(">II", blob, pos)
            pos += 8
            end = blob.index(0, strings_off + offset)
            key = blob[strings_off + offset : end].decode()
            value = blob[pos : pos + size]
            pos = (pos + size + 3) & ~3
            yield "/" + "/".join(stack[1:]), key, value
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            return
        else:
            raise ValueError(f"invalid FDT token {token}")
    raise ValueError("missing FDT_END token")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_image(path):
    prefix = "sysupgrade-aliyun_ap8220/"
    with tarfile.open(path, "r:*") as archive:
        names = set(archive.getnames())
        require(prefix + "kernel" in names, "missing sysupgrade kernel")
        require(prefix + "root" in names, "missing sysupgrade root")
        kernel_member = archive.getmember(prefix + "kernel")
        require(kernel_member.size <= 16 * 1024 * 1024, "kernel exceeds transition setup's 16 MiB volume")
        kernel = archive.extractfile(kernel_member).read()
        root = archive.extractfile(prefix + "root")
        require(root.read(4) == b"hsqs", "root is not SquashFS")

    check_fit(kernel, path.name)


def check_fit(kernel, name):
    fit = {(node, key): value for node, key, value in fdt_properties(kernel)}
    config = fit.get(("/configurations/config@ac02", "fdt"), b"").rstrip(b"\0").decode()
    require(config, "missing config@ac02 FDT selection")
    dtb = fit.get((f"/images/{config}", "data"))
    require(dtb is not None, f"missing FIT FDT image {config}")
    props = {(node, key): value for node, key, value in fdt_properties(dtb)}

    partitions = [
        node for node, key, value in fdt_properties(dtb)
        if key == "compatible" and node.endswith("/nand@0/partitions")
    ]
    require(len(partitions) == 1, "expected one NAND fixed-partitions node")
    parent = partitions[0]
    nand = parent.rsplit("/", 1)[0]
    require(props.get((nand, "nand-ecc-strength")) == struct.pack(">I", 8),
            "NAND ECC strength must be 8 bits to match the transition writer")
    require(props.get((nand, "nand-ecc-step-size")) == struct.pack(">I", 512),
            "NAND ECC step size must be 512 bytes")
    require(props[(parent, "compatible")] == b"fixed-partitions\0", "NAND still uses SMEM partitions")

    for node_name, label, offset, size in (
        ("partition@0", b"QWRT\0", 0, 0x3E800000),
        ("partition@3e800000", b"ubi_kernel\0", 0x3E800000, 0x01800000),
    ):
        node = f"{parent}/{node_name}"
        require(props.get((node, "label")) == label, f"wrong label for {node_name}")
        require(props.get((node, "reg")) == struct.pack(">II", offset, size),
                f"wrong offset/size for {node_name}")

    bootargs = props.get(("/chosen", "bootargs-append"), b"")
    require(b"root=/dev/ubiblock0_1" in bootargs,
            "rootfs boot argument does not select UBI volume 1")
    print(f"OK: {name}: QWRT 1000 MiB, ubi_kernel 24 MiB, root volume 1, ECC 8/512")


def main():
    directory = Path(sys.argv[1])
    images = list(directory.glob("*aliyun_ap8220*sysupgrade*.bin"))
    require(len(images) == 1, f"expected one AP8220 sysupgrade image, found {len(images)}")
    initramfs = list(directory.glob("*aliyun_ap8220*initramfs*.itb"))
    require(len(initramfs) == 1, f"expected one AP8220 initramfs ITB, found {len(initramfs)}")
    factory = list(directory.glob("*aliyun_ap8220*factory.ubi"))
    require(not factory, "split-UBI AP8220 build must not publish a single factory UBI")
    check_image(images[0])
    check_fit(initramfs[0].read_bytes(), initramfs[0].name)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, IndexError, struct.error) as error:
        print(f"AP8220 1G validation failed: {error}", file=sys.stderr)
        sys.exit(1)
