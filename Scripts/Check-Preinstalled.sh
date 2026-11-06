#!/bin/bash
# Run prepare in the OpenWrt source root, after package customization and before defconfig.
# Recovers the selected LuCI theme source when the configured feeds do not provide it.
set -euo pipefail

case "${1:-}" in
  prepare)
    theme="${WRT_THEME:?Resolve WRT_THEME before preparing preinstalled packages}"
    [[ "$theme" != auto ]] || { echo "::error::WRT_THEME must be resolved first" >&2; exit 1; }
    package="luci-theme-$theme"
    # Standard LuCI packages use luci.mk macros in a directory named after the package.
    # feeds/luci may not exist yet; a missing directory is not an error here.
    found="$(find package feeds/luci -type f -path "*/$package/Makefile" -print -quit 2>/dev/null || true)"
    if [[ -z "$found" ]]; then
      case "$theme" in
        vantage)
          git clone --depth=1 --single-branch --branch main \
            https://github.com/anothaDev/luci-theme-vantage.git package/luci-theme-vantage
          ;;
        *)
          # Prefer the configured feed rather than guessing an external repository.
          ./scripts/feeds install "$package"
          ;;
      esac
      found="$(find package feeds/luci -type f -path "*/$package/Makefile" -print -quit 2>/dev/null || true)"
      [[ -n "$found" ]] || { echo "::error::Missing $package; no source was provided by its feed" >&2; exit 1; }
    fi
    echo "Preinstalled theme source: $found"
    ;;
  *) echo "Usage: $0 prepare" >&2; exit 2 ;;
esac
