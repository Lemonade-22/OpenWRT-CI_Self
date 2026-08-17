#!/bin/bash
# SPDX-License-Identifier: MIT
# Nokia XG-040G-MD NWRT hardware layer
# Hardware source: bingoguo93/immortalwrt 6.18
# Exact hardware commit: 97943af2969696d772a6ad7a82eda22e06d23514

set -euo pipefail

cd "$GITHUB_WORKSPACE/wrt"

BINGO_REPO="https://github.com/bingoguo93/immortalwrt.git"
BINGO_COMMIT="97943af2969696d772a6ad7a82eda22e06d23514"

# This commit is the NWRT hardware delta on top of the common ImmortalWrt base.
# Copy only the files changed by that commit so the VIKING owrt tree remains the
# software base while the XG-040G hardware definition comes from bingo.
git remote remove bingo-xg040g 2>/dev/null || true
git remote add bingo-xg040g "$BINGO_REPO"
git fetch --no-tags bingo-xg040g "$BINGO_COMMIT"

FILES=(
  "package/base-files/files/etc/uci-defaults/99_fix-airoha-mac"
  "package/boot/uboot-tools/uboot-envtools/files/airoha_an7581"
  "target/linux/airoha/an7581/base-files/etc/board.d/01_leds"
  "target/linux/airoha/an7581/base-files/etc/board.d/02_network"
  "target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh"
  "target/linux/airoha/dts/an7581-nokia_xg-040g-md-common-nwrt-ubi-parts.dtsi"
  "target/linux/airoha/dts/an7581-nokia_xg-040g-md-common-nwrt.dtsi"
  "target/linux/airoha/dts/an7581-nokia_xg-040g-md.dts"
  "target/linux/airoha/dts/an7581-nokia_xg-040g-tf.dts"
  "target/linux/airoha/dts/an7581-nokia_xg-140g-md.dts"
  "target/linux/airoha/dts/an7581-nokia_xg-140g-tf.dts"
  "target/linux/airoha/dts/an7581-npu.dtsi"
  "target/linux/airoha/dts/an7581.dtsi"
  "target/linux/airoha/image/an7581.mk"
)

echo "Applying bingo NWRT hardware layer: $BINGO_COMMIT"
git checkout "$BINGO_COMMIT" -- "${FILES[@]}"

git diff --check

grep -q 'Device/nokia_xg-040g-md-common-nwrt' target/linux/airoha/image/an7581.mk
grep -q 'an7581-nokia_xg-040g-md-common-nwrt.dtsi' target/linux/airoha/dts/an7581-nokia_xg-040g-md.dts
grep -q 'an7581-nokia_xg-040g-md-common-nwrt-ubi-parts.dtsi' target/linux/airoha/dts/an7581-nokia_xg-040g-md.dts

echo "Bingo NWRT hardware layer applied successfully."

# Keep the cache/release identity tied to the hardware layer as well as the
# VIKING source commit, even though HEAD itself is intentionally unchanged.
echo "WRT_HASH=$(git log -1 --pretty=format:'%h')-bingo-${BINGO_COMMIT:0:8}" >> "$GITHUB_ENV"
