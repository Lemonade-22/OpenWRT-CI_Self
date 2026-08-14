#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G / XG-140G hardware support.
#
# VIKINGYFY/immortalwrt (owrt) remains the firmware base.
# XG-040G hardware and NPU integration are taken from bingo's verified 6.18 tree.
# Generic VIKING AN7581 support remains untouched unless explicitly replaced below.

set -e

if [[ "${WRT_CONFIG:-}" != "AIROHA-WIFI-NO" ]]; then
    exit 0
fi

WRT="$GITHUB_WORKSPACE/wrt"
DTS="$WRT/target/linux/airoha/dts"
IMAGE="$WRT/target/linux/airoha/image/an7581.mk"
BINGO_RAW="https://raw.githubusercontent.com/bingoguo93/immortalwrt/6.18/target/linux/airoha"

mkdir -p "$DTS" "$(dirname "$IMAGE")"

# Use bingo's complete XG-040G hardware/NPU DTS layer.
# In particular, the NPU DTS is intentionally taken from bingo rather than
# VIKING: the user's requirement is to reproduce bingo's known-working NPU
# integration. Do not retain VIKING's an7581-npu-mt7992.dtsi here.
for FILE in \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-xg-140g-md.dts \
    an7581-xg-040g-tf.dts \
    an7581-xg-140g-tf.dts \
    an7581-npu-mt7992.dtsi; do
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

echo "Applied bingo XG-040G/140G hardware and NPU layer on top of VIKING owrt."
echo "Preserved VIKING generic AN7581 DTS, network scripts and image definitions."
echo "Replaced the VIKING AN7581 MT7992 NPU DTS with bingo's verified NPU DTS."
echo "Removed unavailable kmod-i2c-an7581 from imported bingo device package lists."
