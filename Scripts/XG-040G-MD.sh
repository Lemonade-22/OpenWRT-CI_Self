#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G-MD hardware layer.
#
# VIKINGYFY/immortalwrt (owrt) remains the firmware base.
# XG-040G-MD hardware, NAND and NPU integration are taken from bingo's
# verified 6.18 tree.
#
# First validation build intentionally targets XG-040G-MD only. 040G/140G
# WAN-layout differences and TF variants are deferred until the base MD
# hardware is verified.

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
# The NPU DTS is intentionally taken from bingo rather than VIKING.
for FILE in \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-npu-mt7992.dtsi; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# Do not overwrite VIKING's complete an7581.mk. Import only the
# XG-040G-MD device definition and preserve the VIKING/upstream image tree.
TMP="$(mktemp)"
TMP_CLEAN="$(mktemp)"
trap 'rm -f "$TMP" "$TMP_CLEAN"' EXIT
curl -fsSL "$BINGO_RAW/image/an7581.mk" -o "$TMP"

# The imported bingo device definition references kmod-i2c-an7581, which is
# not present in the VIKING package tree. Remove only that package reference.
sed 's/kmod-i2c-an7581[[:space:]]*//g' "$TMP" > "$TMP_CLEAN"

DEVICE="bell_xg-040g-md"
if grep -q "^TARGET_DEVICES += $DEVICE$" "$IMAGE"; then
    echo "Device $DEVICE already exists; keeping the VIKING definition."
else
    awk -v device="$DEVICE" '
        $0 ~ "^define Device/" device "$" { found=1 }
        found { print }
        found && $0 == "TARGET_DEVICES += " device { exit }
    ' "$TMP_CLEAN" >> "$IMAGE"
fi

echo "Applied bingo XG-040G-MD hardware/NPU layer on top of VIKING owrt."
echo "Preserved VIKING generic AN7581 DTS, network scripts and image definitions."
echo "NPU DTS is bingo's verified version; VIKING WLAN NPU reserved-memory is not imported."
echo "Initial build target: XG-040G-MD only."
