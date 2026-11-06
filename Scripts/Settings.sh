#!/bin/bash
# Run in the OpenWrt source root, before make defconfig.
#
# VIKINGYFY/OpenWRT-CI's Scripts/Settings.sh stays authoritative: it is fetched
# at build time and executed as-is. A vendored copy cannot follow upstream, and
# the previous one silently lost the "enable luci-app-<theme>" line, which is
# exactly where a theme's dashboard lives (vantage's overview page).
#
# Local behaviour that must survive lives in Scripts/Settings-Extra.sh and runs
# afterwards; it only adds, never rewrites upstream logic.
#
# No profile is special-cased: whatever upstream decides for WIFI-NO images is
# what this build does, ZN-M2 included. The old local exception (keep the stock
# qualcommax DTS for ZN-M2-WIFI-NO) is gone on purpose.
set -eo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(printenv WRT_UPSTREAM_REPO || true)"
[ -n "$repo" ] || repo="VIKINGYFY/OpenWRT-CI"
ref="$(printenv WRT_UPSTREAM_REF || true)"
[ -n "$ref" ] || ref="main"

cache="$(printenv RUNNER_TEMP || true)"
[ -n "$cache" ] || cache="/tmp"
cache="$cache/upstream-settings"
mkdir -p "$cache"
script="$cache/Settings.sh"

echo "Settings.sh: fetching $repo@$ref"
if ! curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 20 -o "$script" \
  "https://raw.githubusercontent.com/$repo/$ref/Scripts/Settings.sh"; then
  echo "::error::cannot fetch Scripts/Settings.sh from $repo@$ref" >&2
  exit 1
fi
# An HTML error page would curl fine but bash would fail on the first line, so
# fail early with a message that names the real problem.
if ! head -n 1 "$script" | grep -q '^#!'; then
  echo "::error::$repo@$ref Scripts/Settings.sh does not look like a shell script" >&2
  exit 1
fi

bash -eo pipefail "$script"

bash -eo pipefail "$here/Settings-Extra.sh"
