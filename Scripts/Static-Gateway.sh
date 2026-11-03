#!/bin/bash
# Run from the firmware source root after package overrides and around defconfig.
set -euo pipefail

symbol=CONFIG_PACKAGE_luci-app-static-gw
package_dir=package/luci-app-static-gw

case "${1:-}" in
  configure)
    git clone --depth=1 --single-branch --branch main \
      https://github.com/Lemonade-22/luci-app-static-gw.git "$package_dir"
    echo "luci-app-static-gw source: $(git -C "$package_dir" rev-parse HEAD)"
    sed -i -E "/^(# )?${symbol}(=| )/d" .config
    printf '%s\n' "${symbol}=y" >> .config
    ;;
  verify)
    grep -qxF "${symbol}=y" .config || {
      echo "::error::luci-app-static-gw is not built into the resolved firmware configuration"
      exit 1
    }
    ;;
  *)
    echo "Usage: $0 {configure|verify}" >&2
    exit 2
    ;;
esac
