#!/bin/bash
# XG-040G/140G hardware support overlay.
# Base OS remains VIKINGYFY/immortalwrt (owrt).
# Hardware definitions are taken from bingoguo93/immortalwrt 6.18,
# which is the known-good XG-040G-MD family implementation.

set -e

if [[ "${WRT_CONFIG:-}" != "AIROHA-WIFI-NO" ]]; then
    exit 0
fi

WRT="$GITHUB_WORKSPACE/wrt"
DTS="$WRT/target/linux/airoha/dts"
IMAGE="$WRT/target/linux/airoha/image/an7581.mk"
PREINIT="$WRT/target/linux/airoha/base-files/lib/preinit"
BINGO_RAW="https://raw.githubusercontent.com/bingoguo93/immortalwrt/6.18/target/linux/airoha"

mkdir -p "$DTS" "$(dirname "$IMAGE")" "$PREINIT"

# Use bingo's verified XG-040G/140G hardware layer.
curl -fsSL "$BINGO_RAW/dts/an7581-xg-040g-series.dtsi" -o "$DTS/an7581-xg-040g-series.dtsi"
for DEVICE in 040g-md 140g-md 040g-tf 140g-tf; do
    curl -fsSL "$BINGO_RAW/dts/an7581-xg-${DEVICE}.dts" -o "$DTS/an7581-xg-${DEVICE}.dts"
done

# Keep bingo's complete AN7581 image definitions so the four device images
# are generated together. This replaces the older VIKING-only Nokia definition.
curl -fsSL "$BINGO_RAW/image/an7581.mk" -o "$IMAGE"

# Network device labels used by bingo are also present in the upstream tree;
# install the known-good copy explicitly for deterministic builds.
curl -fsSL "$BINGO_RAW/base-files/lib/preinit/04_set_netdev_label" -o "$PREINIT/04_set_netdev_label"

# The bingo configuration uses these four device symbols in one build.
# NPU firmware is selected in Config/AIROHA-WIFI-NO.txt.

echo "Applied bingo XG-040G/140G hardware support on top of VIKING owrt."
