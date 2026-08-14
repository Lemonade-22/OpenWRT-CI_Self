#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G / XG-140G hardware support.
#
# The firmware base remains VIKINGYFY/immortalwrt (owrt).
# For the Airoha XG-040G family, use the known-good hardware layer from
# bingoguo93/immortalwrt 6.18 directly instead of maintaining a parallel
# hand-written DTS/NAND implementation in this repository.

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

# The XG-040G series DTS is self-contained around these two common includes.
# Copy them from bingo as well so VIKING's owrt version cannot silently supply
# a different AN7581/NPU base DTS.
for FILE in \
    an7581.dtsi \
    an7581-npu-mt7992.dtsi \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-xg-140g-md.dts \
    an7581-xg-040g-tf.dts \
    an7581-xg-140g-tf.dts; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# Use bingo's complete AN7581 image definitions. This provides the four
# common XG-040G-family targets and their verified 256M NAND image layout.
curl -fsSL "$BINGO_RAW/image/an7581.mk" -o "$IMAGE"

# Keep bingo's deterministic network-device naming preinit hook.
curl -fsSL "$BINGO_RAW/base-files/lib/preinit/04_set_netdev_label" \
    -o "$PREINIT/04_set_netdev_label"

# The four targets are intentionally built from one common configuration:
#   XG-040G-MD  : USB, default network
#   XG-140G-MD  : USB, LAN4 as WAN
#   XG-040G-TF  : no USB, default network
#   XG-140G-TF  : no USB, LAN4 as WAN

echo "Applied bingo XG-040G/140G hardware layer on top of VIKING owrt."
