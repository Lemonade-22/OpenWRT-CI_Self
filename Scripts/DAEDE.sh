#!/bin/bash
# Run in the OpenWrt source root; keep MT7621 untouched.
#
# Nothing is shipped into the image any more: no daed, no luci-app-daede, and no
# geo databases. This script only prepares the .config:
#
#   * applies the eBPF kernel prerequisites from Config/DAEDE.txt, so a daed or
#     dae the user installs later works out of the box;
#   * keeps daed, dae and luci-app-daede explicitly unselected, so the firmware
#     never carries a backend with no front end (or front end with no backend).
#
# Geo data used to be baked in here (daed looks for it under
# /usr/share/v2ray). It costs about 10 MiB of squashfs, which comes straight out
# of the writable overlay on small-flash NAND boxes, so it is gone: install the
# data the same way you install daed.
set -euo pipefail

ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"

die() { echo "::error::$*" >&2; exit 1; }

apply_requirements() {
  local option symbol
  while IFS= read -r option; do
    case "$option" in
      CONFIG_*=*|"# CONFIG_"*" is not set") ;;
      *) continue ;;
    esac
    symbol="${option%%=*}"
    sed -i -E "/^(# )?${symbol}(=| )/d" .config
    printf '%s\n' "$option" >> .config
  done < "$ci_root/Config/DAEDE.txt"
}

case "${1:-}" in
  configure)
    if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
      echo "Skipping daed prerequisites on MT7621"
      exit 0
    fi
    apply_requirements

    # Netkit is optional on older source branches.
    if grep -q '^config KERNEL_NETKIT$' config/Config-kernel.in; then
      sed -i -E '/^(# )?CONFIG_KERNEL_NETKIT(=| )/d' .config
      echo 'CONFIG_KERNEL_NETKIT=y' >> .config
    fi

    # Config/DAEDE.txt and the de-selection lines can both emit the same
    # "# CONFIG_X is not set"; keep a single copy of each.
    awk '/^# CONFIG_.* is not set$/{ if (seen[$0]++) next } { print }' .config > .config.dedup
    mv .config.dedup .config
    echo "daed prerequisites applied; no daed, no geo data in the image"
    ;;

  verify)
    grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile" && exit 0

    # Nothing is staged any more; only the .config work has to hold.
    [ ! -e "./files/usr/bin/daed" ] || die "files/usr/bin/daed reappeared; nothing should stage a backend"
    [ ! -e "./files/usr/share/v2ray/geoip.dat" ] || die "files/usr/share/v2ray/geoip.dat reappeared; geo data is no longer baked in"

    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=y)
          grep -qxF "$option" .config || { echo "::error::Missing required eBPF dependency: $option" >&2; exit 1; }
          ;;
        "# CONFIG_"*" is not set")
          symbol="${option#\# }"
          symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting eBPF dependency: $symbol" >&2; exit 1
          fi
          ;;
      esac
    done < "$ci_root/Config/DAEDE.txt"
    echo "Verified: daed prerequisites only, no backend and no geo data"
    ;;

  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
