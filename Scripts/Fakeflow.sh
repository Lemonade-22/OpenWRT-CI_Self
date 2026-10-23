#!/bin/bash
# Run from the firmware source root, after user overrides and around defconfig.
set -euo pipefail
case "${WRT_CONFIG:?WRT_CONFIG required}" in
  IPQ807X-AP8220-1G-WIFI-NO|ZN-M2-WIFI-NO|N60-Pro-512M|AIROHA-MD-NATIVE|AIROHA-NWRT|Panther-X2-OPhub) ;;
  *) exit 0 ;;
esac
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-}" in
  configure|verify) ;;
  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
while IFS= read -r option; do
  case "$option" in CONFIG_*=y) ;; *) continue ;; esac
  if [ "$1" = configure ]; then
    symbol="${option%%=*}"
    sed -i -E "/^(# )?${symbol}(=| )/d" .config
    printf '%s\n' "$option" >> .config
  else
    grep -qxF "$option" .config || {
      echo "::error::Missing fake-flow runtime dependency: $option"
      exit 1
    }
  fi
done < "$ci_root/Config/FAKEFLOW.txt"
