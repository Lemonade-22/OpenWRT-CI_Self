#!/bin/bash
# Run from the OpenWrt source root; keep MT7621 untouched.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"
if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
  echo "Skipping dae/daed integration for MT7621"
  exit 0
fi
required="$ci_root/Config/DAEDE.txt"
case "${1:-}" in
  prepare)
    test -f scripts/feeds
    ./scripts/feeds uninstall dae daed luci-app-daed luci-app-daede vmlinux-btf
    for pkg in dae daed luci-app-daed luci-app-daede vmlinux-btf; do
      find feeds -mindepth 2 -maxdepth 4 -type d -name "$pkg" -prune -exec rm -rf -- {} +
    done
    test ! -e package/openwrt-daede
    git init package/openwrt-daede
    git -C package/openwrt-daede remote add origin https://github.com/kenzok8/openwrt-daede.git
    git -C package/openwrt-daede fetch --depth=1 origin a696f20ec4e1887439cbc6bd67db31525591d24a
    git -C package/openwrt-daede checkout --detach FETCH_HEAD
    mkdir -p files/etc/daed
    chmod 750 files/etc/daed
    ;;
  configure)
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
    # Netkit is optional; older source branches may not expose this symbol.
    if grep -q '^config KERNEL_NETKIT
    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=y)
          grep -qxF "$option" .config || { echo "::error::Missing required dae/daed option: $option"; exit 1; }
          ;;
        "# CONFIG_"*" is not set")
          symbol="${option#\# }"; symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting dae/daed option: $symbol"; exit 1
          fi
          ;;
      esac
    done < "$required"
    ;;
  *) echo "Usage: $0 prepare|configure|verify" >&2; exit 2 ;;
esac
 config/Config-kernel.in; then
      sed -i -E '/^(# )?CONFIG_KERNEL_NETKIT(=| )/d' .config
      echo 'CONFIG_KERNEL_NETKIT=y' >> .config
    fi
    ;;
  verify)
    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=y)
          grep -qxF "$option" .config || { echo "::error::Missing required dae/daed option: $option"; exit 1; }
          ;;
        "# CONFIG_"*" is not set")
          symbol="${option#\# }"; symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting dae/daed option: $symbol"; exit 1
          fi
          ;;
      esac
    done < "$required"
    ;;
  *) echo "Usage: $0 prepare|configure|verify" >&2; exit 2 ;;
esac
