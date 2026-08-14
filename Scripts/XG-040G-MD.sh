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
# Keep VIKING's an7581.dtsi and NPU DTS intact; the series DTS includes them.
for FILE in \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-xg-140g-md.dts \
    an7581-xg-040g-tf.dts \
    an7581-xg-140g-tf.dts; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# Do not overwrite VIKING's complete an7581.mk.  Append only bingo's four
# XG-040G-family device definitions, preserving all VIKING/upstream devices.
TMP="$(mktemp)"
curl -fsSL "$BINGO_RAW/image/an7581.mk" -o "$TMP"

for DEVICE in bell_xg-040g-md bell_xg-140g-md bell_xg-040g-tf bell_xg-140g-tf; do
    if grep -q "^TARGET_DEVICES += $DEVICE$" "$IMAGE"; then
        echo "Device $DEVICE already exists; keeping the VIKING definition."
        continue
    fi

    awk -v device="$DEVICE" '
        $0 ~ "^define Device/" device "$" { found=1 }
        found { print }
        found && $0 == "TARGET_DEVICES += " device { exit }
    ' "$TMP" >> "$IMAGE"

done

rm -f "$TMP"

echo "Applied bingo XG-040G/140G hardware layer on top of VIKING owrt."
echo "Preserved VIKING AN7581 base DTS, NPU DTS, network scripts and image definitions."
