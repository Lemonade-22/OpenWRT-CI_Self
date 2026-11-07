#!/bin/bash
# Run in the OpenWrt source root; keep MT7621 untouched.
#
# Ships ONLY the geo databases into the image. daed and luci-app-daede are not
# installed by the firmware any more: they are not in apk's installed database,
# so the daede panel reported them as "not installed" while the files sat in the
# rootfs, and a half-installed panel is worse than none. Users who want daed
# install it from its feed, and the kernel prerequisites in Config/DAEDE.txt
# stay selected so that install works out of the box.
#
#   * geoip.dat  <- v2fly/geoip, China-only list by default (GEOIP_FULL=1 for
#                   the full database from Loyalsoldier)
#   * geosite.dat <- Loyalsoldier/v2ray-rules-dat, full database
#
# Both land in /usr/share/v2ray, which is where dae/daed look
# (DAE_LOCATION_ASSET), and are symlinked into /usr/share/daed for builds that
# ignore that variable.
set -euo pipefail

ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"

# Pinned upstreams. Bump deliberately: these are the versions the image ships.
GEO_REPO="${GEO_REPO:-Loyalsoldier/v2ray-rules-dat}"
GEO_TAG="${GEO_TAG:-202611052203}"
GEOIP_FULL="${GEOIP_FULL:-0}"
GEOIP_CN_REPO="${GEOIP_CN_REPO:-v2fly/geoip}"
GEOIP_CN_TAG="${GEOIP_CN_TAG:-202611050539}"
GEOIP_CN_FILE="geoip-only-cn-private.dat"

# sha256 of each pinned geo file, taken from the release's own .sha256sum.
GEO_SHA_geoip_dat="90b78ab861c1cdc3f871f305f9ceedfb8d6d6329e3a40295e6773e057297384c"
GEO_SHA_geosite_dat="eb694a0dd2afdc7b2a4467402d11cf2e95bc284c7eb8f20d18b25b8068a4c1c0"
GEOIP_CN_SHA="1e847113643114291a31fa467842eafd2185957eddc5d4105ded75a3c68dc21a"

GEO_DIR="/usr/share/v2ray"
ASSET_DIR="/usr/share/daed"
GEO_FILES="geoip.dat geosite.dat"

cache="${RUNNER_TEMP:-/tmp}/daede-prebuilt"
files_root="./files"

die() { echo "::error::$*" >&2; exit 1; }

fetch() {
  local url="$1" out="$2"
  [ -s "$out" ] && { echo "cached: $(basename "$out")"; return 0; }
  echo "fetch: $url"
  curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 20 -o "$out.part" "$url" \
    || die "download failed: $url"
  mv "$out.part" "$out"
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

check_sha() {
  local file="$1" expected="$2" label="$3" actual
  actual="$(sha256_of "$file")"
  [ "$actual" = "$expected" ] \
    || die "$label sha256 mismatch (expected $expected, got $actual); bump the pinned tag and hash together"
  echo "geo: $label $actual"
}

fetch_geoip() {
  # Two distinct cache names: sharing one would let a CN-only run poison the
  # full-database run in the same workspace.
  local src
  if [ "$GEOIP_FULL" = "1" ]; then
    src="$cache/geoip-full.dat"
    fetch "https://github.com/$GEO_REPO/releases/download/$GEO_TAG/geoip.dat" "$src"
    check_sha "$src" "$GEO_SHA_geoip_dat" "geoip.dat (full)"
  else
    src="$cache/$GEOIP_CN_FILE"
    fetch "https://github.com/$GEOIP_CN_REPO/releases/download/$GEOIP_CN_TAG/$GEOIP_CN_FILE" "$src"
    check_sha "$src" "$GEOIP_CN_SHA" "$GEOIP_CN_FILE"
  fi
  install -m 0644 "$src" "$files_root$GEO_DIR/geoip.dat"
}

install_geo() {
  local geo
  mkdir -p "$files_root$GEO_DIR"

  fetch_geoip

  fetch "https://github.com/$GEO_REPO/releases/download/$GEO_TAG/geosite.dat" "$cache/geosite.dat"
  check_sha "$cache/geosite.dat" "$GEO_SHA_geosite_dat" "geosite.dat"
  install -m 0644 "$cache/geosite.dat" "$files_root$GEO_DIR/geosite.dat"

  mkdir -p "$files_root$ASSET_DIR"
  for geo in $GEO_FILES; do
    [ -s "$files_root$GEO_DIR/$geo" ] || die "$GEO_DIR/$geo did not land in the image"
    ln -sfn "../v2ray/$geo" "$files_root$ASSET_DIR/$geo"
  done
}

case "${1:-}" in
  configure)
    if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
      echo "Skipping geo data on MT7621"
      exit 0
    fi
    if [ "$GEOIP_FULL" = "1" ]; then
      echo "Geo data only: geoip FULL $GEO_REPO@$GEO_TAG"
    else
      echo "Geo data only: geoip CN-only $GEOIP_CN_REPO@$GEOIP_CN_TAG"
    fi
    install_geo

    # Kernel prerequisites for a later daed install, plus the explicit
    # de-selection of the packages themselves.
    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=*|"# CONFIG_"*" is not set") ;;
        *) continue ;;
      esac
      symbol="${option%%=*}"
      sed -i -E "/^(# )?${symbol}(=| )/d" .config
      printf '%s\n' "$option" >> .config
    done < "$ci_root/Config/DAEDE.txt"

    if grep -q '^config KERNEL_NETKIT$' config/Config-kernel.in; then
      sed -i -E '/^(# )?CONFIG_KERNEL_NETKIT(=| )/d' .config
      echo 'CONFIG_KERNEL_NETKIT=y' >> .config
    fi

    awk '/^# CONFIG_.* is not set$/{ if (seen[$0]++) next } { print }' .config > .config.dedup
    mv .config.dedup .config
    echo "geo data staged into $files_root: $(du -sh "$files_root$GEO_DIR" | cut -f1)"
    ;;

  verify)
    grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile" && exit 0

    for geo in $GEO_FILES; do
      [ -s "$files_root$GEO_DIR/$geo" ] || die "$GEO_DIR/$geo is missing"
      first="$(head -c 1 "$files_root$GEO_DIR/$geo" | od -An -tx1 | tr -d ' \n')"
      [ "$first" = "0a" ] || die "$GEO_DIR/$geo is not v2ray geodata (first byte: $first)"
      [ -e "$files_root$ASSET_DIR/$geo" ] || die "$ASSET_DIR/$geo mirror is missing"
    done

    # daed must not be pulled back in by any dependency.
    if grep -Eq '^CONFIG_PACKAGE_(daed|dae|luci-app-daede)=y$' .config; then
      die "daed is selected for building, but this firmware ships geo data only"
    fi
    [ ! -e "$files_root/usr/bin/daed" ] \
      || die "$files_root/usr/bin/daed still exists; the prebuilt daed payload should be gone"

    geoip_size="$(wc -c < "$files_root$GEO_DIR/geoip.dat")"
    if [ "$GEOIP_FULL" = "1" ]; then
      [ "$geoip_size" -gt 4000000 ] \
        || die "GEOIP_FULL=1 but geoip.dat is only ${geoip_size} bytes"
    else
      [ "$geoip_size" -gt 100000 ] \
        || die "geoip.dat is only ${geoip_size} bytes; that is not a usable database"
      [ "$geoip_size" -lt 4000000 ] \
        || die "geoip.dat is ${geoip_size} bytes; this build ships the China-only list (set GEOIP_FULL=1 to allow the full one)"
    fi

    while IFS= read -r option; do
      case "$option" in
        CONFIG_*=y)
          grep -qxF "$option" .config || { echo "::error::Missing required eBPF dependency: $option" >&2; exit 1; }
          ;;
        "# CONFIG_"*" is not set")
          symbol="${option#\# }"
          symbol="${symbol% is not set}"
          if grep -Eq "^$symbol=(y|m)$" .config; then
            echo "::error::Conflicting eBPF dependency: $symbol" >&2; exit 1
          fi
          ;;
      esac
    done < "$ci_root/Config/DAEDE.txt"
    echo "Verified geo data only ($geoip_size byte geoip.dat, no daed packages)"
    ;;

  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
