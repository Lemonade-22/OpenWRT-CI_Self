#!/bin/bash
# SPDX-License-Identifier: MIT
# XG-040G-MD hardware layer.
#
# VIKINGYFY/immortalwrt (owrt) remains the firmware base.
# XG-040G-MD hardware, NAND and NPU integration are taken from bingo's
# verified 6.18 tree. Kwrt's verified 040G network/NAND initialization is
# added separately.
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
NETWORK="$WRT/target/linux/airoha/an7581/base-files/etc/board.d/02_network"
PLATFORM="$WRT/target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh"
BINGO_RAW="https://raw.githubusercontent.com/bingoguo93/immortalwrt/6.18/target/linux/airoha"

mkdir -p "$DTS" "$(dirname "$IMAGE")" "$(dirname "$NETWORK")" "$(dirname "$PLATFORM")"

# Use bingo's complete XG-040G hardware/NPU DTS layer.
# The NPU DTS is intentionally taken from bingo rather than VIKING.
for FILE in \
    an7581-xg-040g-series.dtsi \
    an7581-xg-040g-md.dts \
    an7581-npu-mt7992.dtsi; do
    curl -fsSL "$BINGO_RAW/dts/$FILE" -o "$DTS/$FILE"
done

# VIKING's generic AN7581 DTS is retained, but its CPUFreq node needs the
# chip-scu and mcucfg register resources used by the Airoha CPUFreq driver.
# Import only those two resources from bingo's verified AN7581 DTS.
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

# Import Kwrt's verified XG-040G-MD network mapping without replacing the
# rest of VIKING's generic AN7581 network definitions.
if grep -q 'bell,xg-040g-md)' "$NETWORK"; then
    echo "XG-040G-MD network mapping already exists."
else
    sed -i '/^[[:space:]]*\*)/i\	bell,xg-040g-md)\n\t\tucidef_set_interfaces_lan_wan "lan2 lan3 lan4" "eth1"\n\t\t;;' "$NETWORK"
fi

# Import Kwrt's NAND upgrade handling for the AN7581 target.
# Do not overwrite it if the base already provides an equivalent platform file.
if [[ ! -f "$PLATFORM" ]]; then
    cat > "$PLATFORM" <<'EOF'
REQUIRE_IMAGE_METADATA=1

platform_do_upgrade() {
    local board=$(board_name)

    case "$board" in
    *)
        nand_do_upgrade "$1"
        ;;
    esac
}

platform_check_image() {
    return 0
}
EOF
    echo "Installed Kwrt AN7581 NAND platform upgrade support."
else
    echo "Existing AN7581 platform.sh preserved."
fi

echo "Applied bingo XG-040G-MD hardware/NPU layer on top of VIKING owrt."
echo "Applied Airoha CPUFreq chip-scu/mcucfg register resources."
echo "Applied Kwrt XG-040G-MD network mapping and NAND upgrade support."
echo "Preserved VIKING generic AN7581 DTS and image definitions."
echo "NPU DTS is bingo's verified version; VIKING WLAN NPU reserved-memory is not imported."
echo "Initial build target: XG-040G-MD only."