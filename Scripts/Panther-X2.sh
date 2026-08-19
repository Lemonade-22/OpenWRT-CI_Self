#!/bin/bash
set -euo pipefail

# Panther X2 / RK3566 support imported from coolsnowwolf/lede.
# Pinned source commit keeps the hardware support reproducible.
LEDE_COMMIT="e6cc2bedf8745674d6f682bd1b1474bfb7aa81b9"
BASE_URL="https://raw.githubusercontent.com/coolsnowwolf/lede/${LEDE_COMMIT}"

cd "$GITHUB_WORKSPACE/wrt"

# Linux DTS: Panther X2 is already present in modern 6.18 kernels, but copy
# the known-good LEDE DTS into the OpenWrt target tree to guarantee it is used.
DTS_DIR="target/linux/rockchip/files/arch/arm64/boot/dts/rockchip"
mkdir -p "$DTS_DIR"
curl -fsSL "$BASE_URL/target/linux/rockchip/files/arch/arm64/boot/dts/rockchip/rk3566-panther-x2.dts" \
  -o "$DTS_DIR/rk3566-panther-x2.dts"

# Add the LEDE Panther X2 U-Boot support patch.
UBOOT_PATCH_DIR="package/boot/uboot-rockchip/patches"
mkdir -p "$UBOOT_PATCH_DIR"
curl -fsSL "$BASE_URL/package/boot/uboot-rockchip/patches/316-rockchip-rk3566-Add-support-for-panther-x2.patch" \
  -o "$UBOOT_PATCH_DIR/316-rockchip-rk3566-Add-support-for-panther-x2.patch"

# Register Panther X2 as an OpenWrt image target.
IMAGE_MK="target/linux/rockchip/image/armv8.mk"
if ! grep -q '^define Device/panther_x2$' "$IMAGE_MK"; then
  cat >> "$IMAGE_MK" <<'EOF'

# Panther X2 / RK3566 - imported from coolsnowwolf/lede

define Device/panther_x2
  $(Device/rk3566)
  DEVICE_VENDOR := Panther
  DEVICE_MODEL := X2
  DEVICE_DTS := rk3566-panther-x2
  UBOOT_DEVICE_NAME := panther-x2-rk3566
  IMAGE/sysupgrade.img.gz := boot-common | boot-script | pine64-img | gzip | append-metadata
endef
TARGET_DEVICES += panther_x2
EOF
fi

# Register the dedicated Panther X2 U-Boot target. The LEDE patch supplies
# configs/panther-x2-rk3566_defconfig and selects rk3566-panther-x2.dtb.
UBOOT_MK="package/boot/uboot-rockchip/Makefile"
if ! grep -q '^define U-Boot/panther-x2-rk3566$' "$UBOOT_MK"; then
  python3 - "$UBOOT_MK" <<'PY'
from pathlib import Path
p = Path(__import__('sys').argv[1])
s = p.read_text()
block = '''\n# Panther X2 / RK3566\n\ndefine U-Boot/panther-x2-rk3566\n  $(U-Boot/rk3566/Default)\n  NAME:=Panther X2\n  BUILD_DEVICES:= \\\n    panther_x2\nendef\n\n'''
marker = '# RK3568 boards\n'
if marker not in s:
    raise SystemExit('RK3568 marker not found in uboot-rockchip Makefile')
s = s.replace(marker, block + marker, 1)
needle = '  rock-3c-rk3566 \\\n'
if needle not in s:
    raise SystemExit('RK3566 UBOOT_TARGETS marker not found')
s = s.replace(needle, needle + '  panther-x2-rk3566 \\\n', 1)
p.write_text(s)
PY
fi

echo "Panther X2 RK3566 support imported from LEDE ${LEDE_COMMIT}."
grep -n -A9 '^define Device/panther_x2$' "$IMAGE_MK"
grep -n -A7 '^define U-Boot/panther-x2-rk3566$' "$UBOOT_MK"
