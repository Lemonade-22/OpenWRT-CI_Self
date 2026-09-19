#!/bin/bash
# Run from the OpenWrt source root; keep MT7621 untouched.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"
if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
  echo "Skipping additional eBPF requirements for MT7621"
  exit 0
fi
required="$ci_root/Config/DAEDE.txt"
case "${1:-}" in
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
          symbol="${option#\# }"; symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting eBPF dependency: $symbol"; exit 1
          fi
          ;;
      esac
    done < "$required"
    ;;
  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
