#!/bin/bash
# XG-040G-MD 256M customization
# Applied only when WRT_CONFIG is XG-040G-MD-256M.

set -e

if [[ "${WRT_CONFIG:-}" != "XG-040G-MD-256M" ]]; then
    exit 0
fi

ROOT="$GITHUB_WORKSPACE"
WRT="$ROOT/wrt"
PKG="$WRT/package"
DTS="$WRT/target/linux/airoha/dts"
IMAGE="$WRT/target/linux/airoha/image/an7581.mk"
PATCH_DIR="$WRT/target/linux/airoha/patches-6.18"

mkdir -p "$DTS" "$PATCH_DIR"

# XG-040G-MD DTS used by bingoguo93, with the upstream AN7581 NPU dtsi.
cp -f "$ROOT/XG-040G-MD/an7581-xg-040g-series.dtsi" "$DTS/an7581-xg-040g-series-256m.dtsi"
cp -f "$ROOT/XG-040G-MD/an7581-nokia_xg-040g-md-256m.dts" "$DTS/"

# Add a separate 256M device definition.  The normal VIKING XG-040G-MD
# device is intentionally left untouched, including its bootloader artifacts.
if ! grep -q 'TARGET_DEVICES += nokia_xg-040g-md-256m' "$IMAGE"; then
cat >> "$IMAGE" <<'EOF'

define Device/nokia_xg-040g-md-256m
  $(call Device/nokia_xg-040g-md-common)
  DEVICE_MODEL := XG-040G-MD
  DEVICE_VARIANT := 256M
  DEVICE_DTS := an7581-nokia_xg-040g-md-256m
  DEVICE_DTS_CONFIG := config@1
  KERNEL_LOADADDR := 0x80088000
  KERNEL_IN_UBI := 1
  KERNEL_SIZE := 5120k
  UBINIZE_OPTS := -s 2048
  IMAGE_SIZE := 261120k
  IMAGES := factory.bin sysupgrade.bin
  IMAGE/factory.bin := append-kernel | pad-to $$$$(KERNEL_SIZE) | append-ubi
  IMAGE/sysupgrade.bin := sysupgrade-tar | append-metadata
  SOC := an7581
endef
TARGET_DEVICES += nokia_xg-040g-md-256m
EOF
fi

# SkyHigh robust-read workaround.  Skip it if the current upstream already
# contains the workaround.
if ! grep -Rqs 'spinand_read_page_wait' "$WRT/target/linux"; then
    cp -f "$ROOT/XG-040G-MD/600-mtd-spinand-add-skyhigh-robust-read-workaround.patch" "$PATCH_DIR/600-mtd-spinand-add-skyhigh-robust-read-workaround.patch"
fi

# luanmuc's translated Airoha NPU LuCI app.
rm -rf "$PKG/luci-app-airoha-npu" "$PKG/luci-app-airoha-npu.tmp"
git clone --depth=1 --single-branch https://github.com/luanmuc/luci-app-airoha-npu.git "$PKG/luci-app-airoha-npu.tmp"
if [ -d "$PKG/luci-app-airoha-npu.tmp/luci-app-airoha-npu" ]; then
    cp -a "$PKG/luci-app-airoha-npu.tmp/luci-app-airoha-npu" "$PKG/luci-app-airoha-npu"
else
    cp -a "$PKG/luci-app-airoha-npu.tmp/." "$PKG/luci-app-airoha-npu"
fi
rm -rf "$PKG/luci-app-airoha-npu.tmp"

echo "XG-040G-MD 256M customization installed."
