#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G / XG-140G hardware support.
#
# VIKINGYFY/immortalwrt (owrt) remains the firmware base.
# Only the XG-040G-family hardware-specific layer from bingo is injected here.
# Do NOT replace VIKING's generic AN7581 DTS/NPU definitions.

set -e

if [[ "${WRT_CONFIG:-}" != "AIROHA-WIFI-NO" ]]; then
    exit 0
fi

WRT="$GITHUB_WORKSPACE/wrt"
DTS="$WRT/target/linux/airoha/dts"
IMAGE="$WRT/target/linux/airoha/image/an7581.mk"
BINGO_RAW="https://raw.githubusercontent.com/bingoguo93/immortalwrt/6.18/target/linux/airoha"

mkdir -p "$DTS" "$(dirname "$IMAGE")"

# The bingo series DTS contains the XG-040G-specific hardware description:
# PON, GDM/switch/PHY, LEDs, NAND partitioning and the non-fixed-RAM layout.
# It includes VIKING's local an7581.dtsi and an7581-npu-mt7992.dtsi by filename;
# therefore those VIKING files remain untouched.
for FILE in \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-xg-140g-md.dts \
    an7581-xg-040g-tf.dts \
    an7581-xg-140g-tf.dts; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# Do not overwrite VIKING's complete an7581.mk. Append only bingo's four
# XG-040G-family device definitions, preserving all VIKING/upstream devices.
TMP="$(mktemp)"
TMP_CLEAN="$(mktemp)"
trap 'rm -f "$TMP" "$TMP_CLEAN"' EXIT
curl -fsSL "$BINGO_RAW/image/an7581.mk" -o "$TMP"

# bingo's image definitions reference kmod-i2c-an7581, which is not present
# in the VIKING/ImmortalWrt package tree. The XG-040G DTS does not require that
# package for the network/NPU path we are using, so omit only this package from
# the imported device definitions instead of modifying VIKING's package tree.
sed 's/kmod-i2c-an7581[[:space:]]*//g' "$TMP" > "$TMP_CLEAN"

for DEVICE in bell_xg-040g-md bell_xg-140g-md bell_xg-040g-tf bell_xg-140g-tf; do
    if grep -q "^TARGET_DEVICES += $DEVICE$" "$IMAGE"; then
        echo "Device $DEVICE already exists; keeping the VIKING definition."
        continue
    fi

    awk -v device="$DEVICE" '
        $0 ~ "^define Device/" device "$" { found=1 }
        found { print }
        found && $0 == "TARGET_DEVICES += " device { exit }
    ' "$TMP_CLEAN" >> "$IMAGE"
done

echo "Applied bingo XG-040G/140G hardware layer on top of VIKING owrt."
echo "Preserved VIKING AN7581 base DTS, NPU DTS, network scripts and image definitions."
echo "Removed unavailable kmod-i2c-an7581 from imported bingo device package lists."
