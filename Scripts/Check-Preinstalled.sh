#!/bin/bash
# Run prepare in the OpenWrt source root, after package customization and before defconfig.
# The installed hook checks the real rootfs package transaction, including dependencies.
set -euo pipefail

case "${1:-}" in
  prepare)
    theme="${WRT_THEME:?Resolve WRT_THEME before preparing preinstalled packages}"
    [[ "$theme" != auto ]] || { echo "::error::WRT_THEME must be resolved first" >&2; exit 1; }
    package="luci-theme-$theme"
    # Standard LuCI packages use luci.mk macros in a directory named after the package.
    found="$(find package feeds/luci -type f -path "*/$package/Makefile" -print -quit)"
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
      found="$(find package feeds/luci -type f -path "*/$package/Makefile" -print -quit)"
      [[ -n "$found" ]] || { echo "::error::Missing $package; no source was provided by its feed" >&2; exit 1; }
    fi
    echo "Preinstalled theme source: $found"
    cp "${BASH_SOURCE[0]}" scripts/check-preinstalled.sh
    python3 - <<'PY'
from pathlib import Path
path = Path('package/Makefile')
text = path.read_text()
# Preserve OpenWrt's exact package list, ABI versions, keys and architecture.
# env handles the variable assignments at the start of its package-manager command.
hooks = 0
for manager, verb in [('apk', 'add'), ('opkg', 'install')]:
    original = '\t$(call ' + manager + ',$(TARGET_DIR)) ' + verb + ' '
    wrapped = '\tbash "$(TOPDIR)/scripts/check-preinstalled.sh" ' + manager + ' env $(call ' + manager + ',$(TARGET_DIR)) ' + verb + ' '
    if wrapped in text:
        hooks += 1
        continue
    if original not in text:
        if '$(call ' + manager + ',$(TARGET_DIR))' in text:
            raise SystemExit('::error::Cannot locate ' + manager + ' rootfs installation hook')
        continue
    text = text.replace(original, wrapped)
    hooks += 1
if not hooks:
    raise SystemExit("::error::No supported rootfs package installation hook found")
path.write_text(text, newline='\n')
PY
    ;;
  apk|opkg)
    manager="$1"; shift
    [[ $# -gt 0 ]] || { echo "::error::Missing package installation command" >&2; exit 2; }
    option=--simulate
    [[ "$manager" == apk ]] || option=--noaction
    echo "Checking preinstalled packages and dependencies ($manager)..."
    if ! "$@" "$option"; then
      echo "::error::Preinstalled package check failed; see missing packages or dependency conflicts above. Build their sources before packaging." >&2
      exit 1
    fi
    echo "Preinstalled package check passed; installing rootfs packages."
    exec "$@"
    ;;
  *) echo "Usage: $0 prepare|apk COMMAND...|opkg COMMAND..." >&2; exit 2 ;;
esac
