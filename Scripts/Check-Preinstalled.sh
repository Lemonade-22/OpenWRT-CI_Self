#!/bin/bash
# Run prepare in the OpenWrt source root, after package customization and before defconfig.
# Makes sure the selected LuCI theme can actually be built, whatever the theme is.
#
# WRT_THEME must already be resolved (Scripts/Theme.sh turns "auto" into a name).
# The theme is used from package/ or the LuCI feed when present; otherwise its
# source repository is taken from Scripts/themes.txt and cloned in. A theme with
# no source anywhere fails here, before defconfig, instead of at install time.
set -euo pipefail

find_theme() {
  find package feeds/luci -type f -path "*/luci-theme-$theme/Makefile" -print -quit 2>/dev/null || true
}

case "${1:-}" in
  prepare)
    theme="${WRT_THEME:?Resolve WRT_THEME before preparing preinstalled packages}"
    [[ "$theme" != auto ]] || { echo "::error::WRT_THEME must be resolved first" >&2; exit 1; }
    table="${THEME_TABLE:-${BASH_SOURCE[0]%/*}/themes.txt}"
    package="luci-theme-$theme"

    found="$(find_theme)"
    if [[ -n "$found" ]]; then
      echo "Theme source: $found"
      exit 0
    fi

    source_line=""
    if [[ -f "$table" ]]; then
      source_line="$(awk -v name="$theme" '!/^#/ && $1 == name { print $2, $3; exit }' "$table")"
    fi
    if [[ -n "$source_line" ]]; then
      read -r repo branch <<< "$source_line"
      [[ -n "$repo" ]] && [[ -n "$branch" ]] || {
        echo "::error::Malformed themes.txt entry for $theme: $source_line" >&2
        exit 1
      }
      echo "Theme $theme is not in the tree; cloning $repo ($branch)" >&2
      git clone --depth=1 --single-branch --branch "$branch" \
        "https://github.com/$repo.git" "package/${repo#*/}" >&2 || true
      found="$(find_theme)"
    fi

    if [[ -z "$found" ]] && [[ -x ./scripts/feeds ]]; then
      echo "Theme $theme is still missing; asking the configured feeds" >&2
      ./scripts/feeds install "$package" >&2 || true
      found="$(find_theme)"
    fi

    [[ -n "$found" ]] || {
      echo "::error::Cannot build $package: no source in package/, feeds/luci or Scripts/themes.txt. Add its repository to Scripts/themes.txt." >&2
      exit 1
    }
    echo "Theme source: $found"
    ;;
  *) echo "Usage: $0 prepare" >&2; exit 2 ;;
esac
