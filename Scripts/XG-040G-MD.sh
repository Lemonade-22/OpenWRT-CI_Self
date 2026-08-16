#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G-MD hardware layer.
#
# VIKINGYFY/immortalwrt (owrt) remains the firmware base.
# Import the current XG-040G-MD hardware DTS layer from bingo's verified
# 6.18 tree. Keep VIKING's generic AN7581 image definition and packages.

set -e

if [[ "${WRT_CONFIG:-}" != "AIROHA-WIFI-NO" ]]; then
    exit 0
fi

WRT="$GITHUB_WORKSPACE/wrt"
DTS="$WRT/target/linux/airoha/dts"
NETWORK="$WRT/target/linux/airoha/an7581/base-files/etc/board.d/02_network"
PLATFORM="$WRT/target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh"
BINGO_RAW="https://raw.githubusercontent.com/bingoguo93/immortalwrt/6.18/target/linux/airoha"

mkdir -p "$DTS" "$(dirname "$NETWORK")" "$(dirname "$PLATFORM")"

# The old filenames an7581-xg-040g-series.dtsi and an7581-xg-040g-md.dts
# no longer exist in bingo's 6.18 tree.  Since 2026-08-15 the verified
# XG-040G-MD DTS is split into the following files.
for FILE in \
    an7581-nokia_xg-040g-md-common-nwrt.dtsi \
    an7581-nokia_xg-040g-md-common-nwrt-ubi-parts.dtsi \
    an7581-nokia_xg-040g-md.dts \
    an7581-npu.dtsi; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# VIKING's generic AN7581 DTS is retained, but its CPUFreq node needs the
# chip-scu and mcucfg register resources used by the Airoha CPUFreq driver.
VIKING_AN7581="$DTS/an7581.dtsi"
if [[ -f "$VIKING_AN7581" ]] && grep -q 'compatible = "airoha,en7581-cpufreq"' "$VIKING_AN7581"; then
    if grep -q 'reg = <0x0 0x1fa20000 0x0 0x2c0>' "$VIKING_AN7581"; then
        echo "Airoha CPUFreq register resources already present."
    else
        sed -i '/compatible = "airoha,en7581-cpufreq";/i\		reg = <0x0 0x1fa20000 0x0 0x2c0>,\n\t\t      <0x0 0x1efbe000 0x0 0x800>;\n\t\treg-names = "chip-scu", "mcucfg";' "$VIKING_AN7581"
        echo "Added Airoha CPUFreq chip-scu/mcucfg register resources."
    fi
else
    echo "ERROR: VIKING AN7581 DTS or CPUFreq node not found."
    exit 1
fi

# VIKING's owrt branch already contains the correct nokia_xg-040g-md image
# definition. Do not import bingo's an7581.mk, which would unnecessarily
# replace or duplicate VIKING's image definitions.

# Import the verified XG-040G-MD network mapping only when it is missing.
if grep -q 'nokia,xg-040g-md)' "$NETWORK"; then
    echo "XG-040G-MD network mapping already exists."
else
    sed -i '/^[[:space:]]*\*)/i\	nokia,xg-040g-md)\n\t\tucidef_set_interfaces_lan_wan "lan2 lan3 lan4" "eth1"\n\t\t;;' "$NETWORK"
    echo "Installed XG-040G-MD network mapping."
fi

# Keep an existing VIKING platform.sh. If the base does not provide one,
# install the minimal NAND upgrade handler required by XG-040G-MD.
if [[ ! -f "$PLATFORM" ]]; then
    cat > "$PLATFORM" <<'EOF'
REQUIRE_IMAGE_METADATA=1

platform_do_upgrade() {
    nand_do_upgrade "$1"
}

platform_check_image() {
    return 0
}
EOF
    echo "Installed AN7581 NAND platform upgrade support."
else
    echo "Existing AN7581 platform.sh preserved."
fi

echo "Applied current bingo XG-040G-MD hardware/NPU DTS layer on top of VIKING owrt."
echo "Applied Airoha CPUFreq chip-scu/mcucfg register resources."
echo "Preserved VIKING AN7581 image definitions and package tree."
echo "Initial build target: Nokia XG-040G-MD."
