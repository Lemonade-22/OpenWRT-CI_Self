#!/usr/bin/env python3
"""Assemble the 6.18 packer's input from the author's stock header/U-Boot blobs."""
import hashlib
from pathlib import Path
import struct
import sys
import urllib.request
import zlib

REV = 'ac68c3f8ecb2924c3b763a955e8c9820713c1e7e'
BASE = f'https://raw.githubusercontent.com/cnjn/immortalwrt/{REV}/package/firmware/zte/flies/'
HASHES = {
    'sr1010-header.bin': '222ae685f2e2d234c69a73a0cbe23a63ec3d36c617723986160b19cae24fa120',
    'sr1010-uboot.bin': 'fa9e0c74a1f2f3b8e497875b7756432bd6ad8ddc97379d2770c4bf9fa5a73552',
}

def main():
    blobs = {}
    for name, digest in HASHES.items():
        with urllib.request.urlopen(BASE + name, timeout=60) as response:
            blobs[name] = response.read()
        if hashlib.sha256(blobs[name]).hexdigest() != digest:
            raise SystemExit(f'SHA256 mismatch: {name}')
    header, uboot = blobs['sr1010-header.bin'], blobs['sr1010-uboot.bin']
    assert len(header) == 512 and len(uboot) == 0x180000
    assert zlib.crc32(uboot) == struct.unpack_from('<I', header, 0x98)[0]
    assert uboot[0x32b58:0x32b5c] == bytes.fromhex('9476ff97')
    # load_template() only consumes the outer header, version header and U-Boot.
    # The author's packer supplies the new kernel/rootfs and recomputes CRCs.
    Path(sys.argv[1]).write_bytes(bytes.fromhex('999999994444444455555555aaaaaaaa')
                                  + struct.pack('<I', 0) + header + uboot)
    print(f'Template resources: cnjn/immortalwrt@{REV}; both SHA256 checks passed')

if __name__ == '__main__':
    main()
