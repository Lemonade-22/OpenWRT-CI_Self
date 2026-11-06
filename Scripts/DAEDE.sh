#!/bin/bash
# Run in the OpenWrt source root; keep MT7621 untouched.
#
# Installs the daed backend and its LuCI front end on every profile that can
# run it. The dae package is deliberately never selected: daed embeds the same
# dae core plus the dashboard, and both packages read the same UCI config, so
# selecting dae as well would only duplicate the kernel-space core.
#
# v2ray-geoip and v2ray-geosite arrive through daed's own DEPENDS, and
# luci-app-daede ships update-geo.sh plus geo-cron.sh for on-device refreshes.
# No geodata is downloaded here.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"
if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
  echo "Skipping daed on MT7621"
  exit 0
fi

DAEDE_REPO="${DAEDE_REPO:-https://github.com/kenzok8/openwrt-daede.git}"
DAEDE_REF="${DAEDE_REF:-main}"
DAEDE_DIR="package/openwrt-daede"
required="$ci_root/Config/DAEDE.txt"

# luci-app-daede's install step reads ../dae/files/dae.config, so dae/ has to
# stay next to it even though the dae package is never selected. A tree with
# only daed/ and luci-app-daede/ fails late, in the install phase.
ensure_source() {
  local dir
  if [ -d "$DAEDE_DIR/.git" ]; then
    echo "openwrt-daede already checked out: $(git -C "$DAEDE_DIR" rev-parse HEAD)"
    return 0
  fi
  rm -rf "$DAEDE_DIR"
  git clone --depth=1 --single-branch --branch "$DAEDE_REF" "$DAEDE_REPO" "$DAEDE_DIR"
  echo "openwrt-daede source: $(git -C "$DAEDE_DIR" rev-parse HEAD)"
  for dir in dae daed luci-app-daede; do
    if [ ! -d "$DAEDE_DIR/$dir" ]; then
      echo "::error::$DAEDE_DIR/$dir is missing; the daed package tree is incomplete" >&2
      exit 1
    fi
  done
}

case "${1:-}" in
  configure)
    ensure_source
    # daed builds the dae core with bpf2go and links a Go binary.
    if [ ! -f feeds/packages/lang/golang/golang-package.mk ]; then
      echo "::error::feeds/packages has no golang package; daed cannot build" >&2
      exit 1
    fi
    # Replace prior selections, including private overrides, without duplicates.
    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=*) symbol="${option%%=*}" ;;
        "# CONFIG_"*" is not set") symbol="${option#\# }"; symbol="${symbol% is not set}" ;;
        *) continue ;;
      esac
      sed -i -E "/^(# )?${symbol}(=| )/d" .config
      printf '%s\n' "$option" >> .config
    done < "$required"
    # Netkit is optional on older source branches.
    if grep -q '^config KERNEL_NETKIT$' config/Config-kernel.in; then
      sed -i -E '/^(# )?CONFIG_KERNEL_NETKIT(=| )/d' .config
      echo 'CONFIG_KERNEL_NETKIT=y' >> .config
    fi
    ;;
  verify)
    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=y)
          grep -qxF "$option" .config || { echo "::error::Missing required eBPF dependency: $option"; exit 1; }
          ;;
        "# CONFIG_"*" is not set")
          symbol="${option#\# }"
          symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting eBPF dependency: $symbol"; exit 1
          fi
          ;;
      esac
    done < "$required"
    if [ ! -d "$DAEDE_DIR/daed" ]; then
      echo "::error::$DAEDE_DIR/daed is missing after defconfig" >&2
      exit 1
    fi
    if ! grep -qx 'CONFIG_PACKAGE_daed=y' .config; then
      echo "::error::daed was dropped by defconfig; is $DAEDE_DIR/daed readable?" >&2
      exit 1
    fi
    if ! grep -qx 'CONFIG_PACKAGE_luci-app-daede=y' .config; then
      echo "::error::luci-app-daede was dropped by defconfig" >&2
      exit 1
    fi
    if grep -Eq '^CONFIG_PACKAGE_dae=(y|m)$' .config; then
      echo "::error::the dae package is selected; daed already embeds the same core" >&2
      exit 1
    fi
    ;;
  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
