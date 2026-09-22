#!/usr/bin/env python3
"""Use LZMA for NN6000 v2 while retaining its 6 MiB kernel limit."""
from pathlib import Path
import re

def patch(text):
    pattern = r"(?ms)^define Device/link_nn6000-v2\n.*?^endef$"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("Expected exactly one NN6000 v2 image definition")
    block = matches[0].group()
    inherited = "\t$(Device/link_nn6000-common)\n"
    override = "\t$(call Device/FitImageLzma)\n"
    if inherited not in block:
        raise ValueError("NN6000 v2 no longer inherits the expected image layout")
    if override in block:
        return text
    if re.search(r"(?m)^\s*KERNEL\s*[:?+]?=", block):
        raise ValueError("Unexpected NN6000 v2 kernel override; review upstream changes")
    return text[:matches[0].start()] + block.replace(inherited, inherited + override, 1) + text[matches[0].end():]

def main():
    directory = Path("target/linux/qualcommax/image")
    common = (directory / "Makefile").read_text()
    if "define Device/FitImageLzma\n" not in common:
        raise SystemExit("Missing upstream FitImageLzma support")
    path = directory / "ipq60xx.mk"
    original = path.read_text()
    updated = patch(original)
    path.write_text(updated)
    print("NN6000 v2: LZMA FIT enabled; kernel limit and partition layout unchanged")

if __name__ == "__main__":
    main()
