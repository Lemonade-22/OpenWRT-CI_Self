#!/bin/bash
# Run in the OpenWrt source root; keep MT7621 untouched.
#
# Ships daed, its LuCI front end and the geo databases as PINNED prebuilts
# instead of building them from source.
#
#   * daed + luci-app-daede  <- kenzok8/openwrt-daede release
#   * geosite.dat            <- Loyalsoldier/v2ray-rules-dat, full database
#   * geoip.dat              <- v2fly/geoip China-only database by default,
#                               Loyalsoldier's full one with GEOIP_FULL=1
#
# Payloads land in files/, so the image carries them without a Go toolchain
# and without depending on the buildroot package graph. dae itself is never
# shipped: daed embeds the same core and both read the same UCI config.
#
# Why ipk payloads rather than .apk: apk v3 is a signed ADB container that
# needs apk-tools to open, while an ipk is a plain tar every runner can
# unpack. Both carry the same files. daed is a static Go binary and
# luci-app-daede is arch-independent Lua, so a 24.10-built payload is safe on
# an apk-based 25.12 image.
#
# geoip ships the China-only list on purpose: the full database is 16-24 MB
# of squashed flash and a longer first-boot parse, and daed's own default
# config only asks for geoip(cn). A profile that needs geoip(us)/geoip(jp)
# sets GEOIP_FULL=1 and pays for the full list.
set -euo pipefail

ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$ci_root/Config/${WRT_CONFIG:?WRT_CONFIG required}.txt"

# Pinned upstreams. Bump deliberately: these are the versions the image ships.
DAEDE_REPO="${DAEDE_REPO:-kenzok8/openwrt-daede}"
DAEDE_TAG="${DAEDE_TAG:-v2026.11.05-11da219}"
DAEDE_VERSION="${DAEDE_VERSION:-2026.11.05-r1}"
LUCI_DAEDE_VERSION="${LUCI_DAEDE_VERSION:-1.15-r13}"
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

# daed's init script exports DAE_LOCATION_ASSET=/usr/share/v2ray, so that is
# where the .dat files have to live. Older daed builds ignore the variable and
# look only at /usr/share/daed, so both paths are satisfied with a symlink.
GEO_DIR="/usr/share/v2ray"
ASSET_DIR="/usr/share/daed"
GEO_FILES="geoip.dat geosite.dat"

cache="${RUNNER_TEMP:-/tmp}/daede-prebuilt"
files_root="./files"

die() { echo "::error::$*" >&2; exit 1; }

target_arch() {
  local arch
  arch="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES="\(.*\)"$/\1/p' .config | head -n 1)"
  if [ -z "$arch" ]; then
    # The profile files only name board and subtarget; CONFIG_TARGET_ARCH_PACKAGES
    # is produced by defconfig. Resolve it once here instead of failing, because
    # this script runs before the workflow's own defconfig.
    echo "daed: resolving target architecture (first defconfig)" >&2
    make -s defconfig >/dev/null 2>&1 || die "make defconfig failed while resolving the target architecture"
    arch="$(sed -n 's/^CONFIG_TARGET_ARCH_PACKAGES="\(.*\)"$/\1/p' .config | head -n 1)"
  fi
  printf '%s\n' "$arch"
}

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

# An .ipk is a tar holding data.tar.gz (payload) and control.tar.gz (metadata).
unpack_ipk() {
  local ipk="$1" dest="$2" inner
  inner="$(mktemp -d)"
  tar -xf "$ipk" -C "$inner" data.tar.gz 2>/dev/null \
    || die "$(basename "$ipk") is not an ipk (no data.tar.gz)"
  mkdir -p "$dest"
  tar -xzf "$inner/data.tar.gz" -C "$dest" \
    || die "$(basename "$ipk") payload failed to extract"
  rm -rf "$inner"
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

  # Mirror into daed's own asset dir for kernels that ignore DAE_LOCATION_ASSET.
  mkdir -p "$files_root$ASSET_DIR"
  for geo in $GEO_FILES; do
    [ -s "$files_root$GEO_DIR/$geo" ] || die "$GEO_DIR/$geo did not land in the image"
    ln -sfn "../v2ray/$geo" "$files_root$ASSET_DIR/$geo"
  done
}

stage_packages() {
  local arch="$1"
  mkdir -p "$cache" "$files_root"

  fetch "https://github.com/$DAEDE_REPO/releases/download/$DAEDE_TAG/daed_${DAEDE_VERSION}_${arch}.ipk" \
    "$cache/daed.ipk"
  fetch "https://github.com/$DAEDE_REPO/releases/download/$DAEDE_TAG/luci-app-daede_${LUCI_DAEDE_VERSION}_all.ipk" \
    "$cache/luci-app-daede.ipk"

  # Replace only what this script owns, so other files/ content survives.
  rm -rf "$files_root/usr/bin/daed" "$files_root/usr/bin/daed-guard"
  unpack_ipk "$cache/daed.ipk" "$files_root"
  unpack_ipk "$cache/luci-app-daede.ipk" "$files_root"
  install_geo

  # Nothing is compiled, so these must stay unselected or defconfig tries to
  # build a second copy.
  local symbol
  for symbol in CONFIG_PACKAGE_daed CONFIG_PACKAGE_luci-app-daede CONFIG_PACKAGE_dae; do
    sed -i -E "/^(# )?${symbol}(=| )/d" .config
    printf '# %s is not set\n' "$symbol" >> .config
  done
}

case "${1:-}" in
  configure)
    if grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile"; then
      echo "Skipping daed on MT7621"
      exit 0
    fi
    arch="$(target_arch)"
    [ -n "$arch" ] || die "CONFIG_TARGET_ARCH_PACKAGES is missing from .config; run this after the config is seeded"
    if [ "$GEOIP_FULL" = "1" ]; then
      echo "Prebuilt daed for $arch: $DAEDE_REPO@$DAEDE_TAG, geoip FULL $GEO_REPO@$GEO_TAG"
    else
      echo "Prebuilt daed for $arch: $DAEDE_REPO@$DAEDE_TAG, geoip CN-only $GEOIP_CN_REPO@$GEOIP_CN_TAG"
    fi
    stage_packages "$arch"

    # eBPF prerequisites come from Config/DAEDE.txt; re-apply them so the sed
    # above cannot disturb kernel symbols.
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

    # Config/DAEDE.txt and the de-selection above can both emit the same
    # "# CONFIG_X is not set" line; keep a single copy of each.
    awk '/^# CONFIG_.* is not set$/{ if (seen[$0]++) next } { print }' .config > .config.dedup
    mv .config.dedup .config

    echo "daed staged into $files_root: $(ls "$files_root/usr/bin" | tr '\n' ' ')"
    ;;

  verify)
    grep -qx 'CONFIG_TARGET_ramips_mt7621=y' "$profile" && exit 0

    [ -s "$files_root/usr/bin/daed" ] \
      || die "$files_root/usr/bin/daed is missing; the prebuilt daed payload was not staged"

    # A shell script or an HTML error page would sail through a size check,
    # so confirm the entry point really is an ELF image.
    magic="$(head -c 4 "$files_root/usr/bin/daed" | od -An -tx1 | tr -d ' \n')"
    [ "$magic" = "7f454c46" ] || die "usr/bin/daed is not an ELF binary (magic: $magic)"

    for geo in $GEO_FILES; do
      [ -s "$files_root$GEO_DIR/$geo" ] || die "$GEO_DIR/$geo is missing; dae will fail to reload"
      first="$(head -c 1 "$files_root$GEO_DIR/$geo" | od -An -tx1 | tr -d ' \n')"
      [ "$first" = "0a" ] || die "$GEO_DIR/$geo is not v2ray geodata (first byte: $first)"
      [ -e "$files_root$ASSET_DIR/$geo" ] || die "$ASSET_DIR/$geo mirror is missing"
    done

    # Catch the two silent swaps: a CN-only list where a full one was asked
    # for, and the 16 MB database sneaking into a build that budgets for the
    # small one.
    geoip_size="$(wc -c < "$files_root$GEO_DIR/geoip.dat")"
    if [ "$GEOIP_FULL" = "1" ]; then
      [ "$geoip_size" -gt 4000000 ] \
        || die "GEOIP_FULL=1 but geoip.dat is only ${geoip_size} bytes; the full database did not land"
    else
      [ "$geoip_size" -gt 100000 ] \
        || die "geoip.dat is only ${geoip_size} bytes; that is not a usable database"
      [ "$geoip_size" -lt 4000000 ] \
        || die "geoip.dat is ${geoip_size} bytes; this build ships the China-only list (set GEOIP_FULL=1 to allow the full one)"
    fi

    if grep -Eq '^CONFIG_PACKAGE_(daed|luci-app-daede)=y$' .config; then
      die "daed is selected for building although it is shipped prebuilt; expect two conflicting copies"
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
    echo "Verified prebuilt daed payload and geodata ($geoip_size byte geoip.dat)"
    ;;

  *) echo "Usage: $0 configure|verify" >&2; exit 2 ;;
esac
