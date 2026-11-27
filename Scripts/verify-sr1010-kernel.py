#!/usr/bin/env python3
"""CI 闸门：从 SR1010 成品镜像解出内核，确认启动必需驱动（bootinfo/rootfs/sysfs）真的编进去了。
用法: python3 Scripts/verify-sr1010-kernel.py <firmware.bin>
退出码 0 = 通过，1 = 失败。
仅依赖 python3 标准库 + openssl CLI。
"""
import sys, os, struct, subprocess, tempfile, lzma, re

AES_KEY = "SR101038c09ffb98"
NEED = ("zx279133_bootinfo", "zx279133-rootfs", "slot_offset")

def u32(d, o): return struct.unpack_from("<I", d, o)[0]

def parse_fdt(d):
    magic, tot, off_s, off_str, _, _, _, _, sz_str, _ = struct.unpack(">10I", d[:40])
    if magic != 0xD00DFEED:
        raise SystemExit("::error::kernel payload is not a FIT (bad AES key or layout)")
    strings = d[off_str:off_str+sz_str]; pos = off_s; out = []; stack = []
    def s(no):
        e = strings.find(b"\x00", no); return strings[no:e].decode("latin1", "replace")
    while pos + 4 <= len(d):
        tok = struct.unpack(">I", d[pos:pos+4])[0]; pos += 4
        if tok == 1:
            e = d.find(b"\x00", pos); nm = d[pos:e].decode("latin1", "replace"); pos = (e+1+3) & ~3
            stack.append(nm); out.append(("/" + "/".join([x for x in stack if x]), {}))
        elif tok == 2:
            if stack: stack.pop()
        elif tok == 3:
            ln, no = struct.unpack(">II", d[pos:pos+8]); pos += 8
            v = d[pos:pos+ln]; pos = (pos+ln+3) & ~3
            out[-1][1][s(no)] = v
        elif tok == 4: continue
        elif tok == 9: break
        else: break
    return out

def main(path):
    d = open(path, "rb").read()
    hdr = 0x14 + u32(d, 0x10)
    vh = d[hdr:hdr+0x200]
    ksize, kofs = u32(vh, 0x34), u32(vh, 0x38)
    with open(path, "rb") as f:
        f.seek(kofs); blob = f.read(ksize)
    blob = blob[:len(blob) // 16 * 16]
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(blob); src = tf.name
    dst = src + ".dec"
    subprocess.run(["openssl", "enc", "-d", "-aes-128-ecb", "-K", AES_KEY.encode().hex(),
                    "-nopad", "-in", src, "-out", dst], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    fit = open(dst, "rb").read()
    os.unlink(src); os.unlink(dst)

    img = None; fdt = None
    for p, props in parse_fdt(fit):
        if p.endswith("kernel-1"):
            data = props["data"]; comp = props.get("compression", b"none").decode().strip("\x00")
            img = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(data) if comp == "lzma" else data
        if p.endswith("fdt-1"):
            fdt = props["data"]
    if not img:
        raise SystemExit("::error::no kernel-1 subimage in FIT")

    kv = re.search(rb"Linux version [ -~]{0,60}", img)
    print("kernel:", kv.group().decode("latin1") if kv else "unknown")
    if fdt:
        for p, props in parse_fdt(fdt):
            if p == "/":
                print("dtb   :", props.get("model", b"").split(b"\x00")[0].decode("latin1", "replace"))

    missing = [n for n in NEED if not re.search(n.encode(), img)]
    if missing:
        print("::error::kernel is missing boot-critical drivers: " + ", ".join(missing), file=sys.stderr)
        print("::error::the image would panic at root mount — do not ship it", file=sys.stderr)
        return 1
    print("ok: boot-critical drivers present (" + ", ".join(NEED) + ")")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
