#!/usr/bin/env python3
"""Drop ZN M2 wireless defaults and compress its FIT kernel with LZMA."""
from pathlib import Path
import re

WIFI_PACKAGES = (
    "kmod-ath", "kmod-ath11k", "kmod-ath11k-ahb", "kmod-ath11k-pci",
    "ath11k-firmware-ipq6018", "ath11k-firmware-ipq6018-ddwrt",
    "ath11k-firmware-qcn9074", "ath11k-firmware-qcn9074-ddwrt", "wpad-openssl",
)


def main():
    target = Path("target/linux/qualcommax")
    image_mk = target / "image/Makefile"
    if "define Device/FitImageLzma\n" not in image_mk.read_text():
        raise SystemExit("Missing upstream FitImageLzma support")
    nowifi = target / "files/arch/arm64/boot/dts/qcom/ipq6018-nowifi.dtsi"
    if not nowifi.is_file():
        raise SystemExit("The selected source lacks VIKINGYFY's ipq6018-nowifi.dtsi")

    # Per-device rootfs can force target defaults back to m despite .config=n.
    pattern = r"(?<![\w-])(?:" + "|".join(map(re.escape, WIFI_PACKAGES)) + r")(?![\w-])"
    for path in (target / "Makefile", target / "ipq60xx/target.mk"):
        path.write_text(re.sub(pattern, "", path.read_text()))

    path = target / "image/ipq60xx.mk"
    text = path.read_text()
    matches = list(re.finditer(r"(?ms)^define Device/zn_m2\n.*?^endef$", text))
    if len(matches) != 1:
        raise SystemExit("Expected one image definition for zn_m2")
    block = matches[0].group()
    inherited = "\t$(call Device/nand-common)\n"
    lzma = "\t$(call Device/FitImageLzma)\n"
    if inherited not in block:
        raise SystemExit("ZN M2 no longer uses the upstream NAND image layout")
    if lzma not in block:
        block = block.replace(inherited, inherited + lzma, 1)
    removal = "\tDEVICE_PACKAGES += -ipq-wifi-zn_m2\n"
    if removal not in block:
        block = block[:-len("endef")] + removal + "endef"
    path.write_text(text[:matches[0].start()] + block + text[matches[0].end():])

    for name in (".targetinfo", ".config-target.in", ".config-package.in"):
        (Path("tmp") / name).unlink(missing_ok=True)
    print("ZN M2: wireless defaults removed; LZMA FIT enabled")


if __name__ == "__main__":
    main()
