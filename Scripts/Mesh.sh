#!/bin/bash
# Run in the firmware source tree; shared by WRT-CORE-SELF and N60 Pro.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "${1:-}" in
  prepare)
    git clone --depth=1 --single-branch --branch main \
      https://github.com/xxosdev/luci-app-mesh.git package/luci-app-mesh
    # Full OpenSSL wpad includes Mesh and preserves enterprise authentication.
    # Use one provider instead of installing conflicting wpad binaries.
    sed -i 's/+wpad-mesh-openssl/+wpad-openssl/g; s/+batctl /+batctl-full /g' \
      package/luci-app-mesh/Makefile
    echo "luci-app-mesh source: $(git -C package/luci-app-mesh rev-parse HEAD)"
    ;;
  configure|verify)
    # Discover concrete providers from the source used by this build, including
    # default variants that defconfig would otherwise select for a device.
    mapfile -t providers < <(sed -nE \
      's/^define Package\/((wpad|hostapd|wpa-supplicant)(-[a-z0-9]+)*)$/\1/p' \
      package/network/services/hostapd/Makefile)
    for provider in "${providers[@]}" batctl-tiny batctl-default; do
      case "$provider" in wpad-openssl|hostapd-common|hostapd-utils) continue ;; esac
      symbol="CONFIG_PACKAGE_$provider"
      if [ "$1" = configure ]; then
        sed -i -E "/^(# )?${symbol}(=| )/d" .config
        printf '# %s is not set\n' "$symbol" >> .config
      elif grep -qxF "$symbol=y" .config; then
        echo "::error::Conflicting Mesh provider selected: $provider" >&2
        exit 1
      fi
    done
    while IFS= read -r option; do
      case "$option" in CONFIG_*=y) ;; *) continue ;; esac
      if [ "$1" = configure ]; then
        symbol="${option%%=*}"
        sed -i -E "/^(# )?${symbol}(=| )/d" .config
        printf '%s\n' "$option" >> .config
      elif ! grep -qxF "$option" .config; then
        echo "::error::Missing Mesh dependency after defconfig: $option" >&2
        exit 1
      fi
    done < "$ci_root/Config/MESH.txt"
    ;;
  *) echo "Usage: $0 prepare|configure|verify" >&2; exit 2 ;;
esac
