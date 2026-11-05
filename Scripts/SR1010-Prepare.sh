#!/bin/bash
# Run in the checked-out firmware source tree.
set -euo pipefail

# Keep the board's pinned LuCI fork and its client-flow statistics. Only import
# the same Footstrap theme used by MT7621 from ImmortalWrt's current LuCI feed.
git clone --depth=1 --filter=blob:none --sparse https://github.com/immortalwrt/luci.git "$RUNNER_TEMP/sr1010-luci"
git -C "$RUNNER_TEMP/sr1010-luci" sparse-checkout set themes/luci-theme-footstrap
cp -a "$RUNNER_TEMP/sr1010-luci/themes/luci-theme-footstrap" feeds/luci/themes/
./scripts/feeds install luci-theme-footstrap

# These are the extra applications selected by MT7621 after its exclusions.
git clone --depth=1 https://github.com/4IceG/luci-app-mini-diskmanager.git package/luci-app-mini-diskmanager
git clone --depth=1 https://github.com/sirpdboy/luci-app-partexp.git package/luci-app-partexp
git clone --depth=1 https://github.com/muink/openwrt-natmapt.git package/openwrt-natmapt
git clone --depth=1 https://github.com/muink/openwrt-stuntman.git package/openwrt-stuntman
git clone --depth=1 https://github.com/muink/luci-app-natmapt.git package/luci-app-natmapt

cat "$GITHUB_WORKSPACE/Config/ZTE-SR1010.txt" "$GITHUB_WORKSPACE/Config/GENERAL.txt" > .config
# Reuse MT7621's exact package exclusions/theme overrides without accepting
# its platform selection. PyYAML is installed by the workflow.
python3 - <<'PY'
import os, pathlib, yaml
root = pathlib.Path(os.environ['GITHUB_WORKSPACE'])
workflow = yaml.safe_load((root / '.github/workflows/MT7621.yml').read_text())
overrides = workflow['jobs']['build']['with']['WRT_PACKAGE']
with open('.config', 'a') as config:
    config.write('\n' + '\n'.join(line for line in overrides.splitlines()
                                 if line.startswith('CONFIG_')) + '\n')
PY
# User input adjusts packages only; it cannot silently switch the target.
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ "$line" =~ ^CONFIG_PACKAGE_[A-Za-z0-9_+.-]+=(y|m|n)$ ]]; then
    printf '%s\n' "$line" >> .config
  else
    echo "Invalid package override: $line" >&2
    exit 1
  fi
done <<< "${WRT_PACKAGE:-}"
printf 'CONFIG_PACKAGE_luci=y\nCONFIG_LUCI_LANG_zh_Hans=y\nCONFIG_PACKAGE_luci-theme-footstrap=y\n' >> .config

# The board's first-boot scripts otherwise select Argon and then Design.
sed -i 's|/luci-static/argon|/luci-static/footstrap|g' target/linux/zte/zx279133/base-files/etc/uci-defaults/98-sr1010-defaults
rm target/linux/zte/zx279133/base-files/etc/uci-defaults/99-zx279133-theme
sed -i "s/hostname='.*'/hostname='OWRT'/" package/base-files/files/bin/config_generate
sed -i 's/luci-theme-bootstrap/luci-theme-footstrap/g' feeds/luci/collections/luci/Makefile
sed -i 's|/luci-static/bootstrap|/luci-static/footstrap|g' feeds/luci/modules/luci-base/root/etc/config/luci

cp .config "$RUNNER_TEMP/sr1010-requested.config"
make defconfig
for symbol in TARGET_zte TARGET_zte_zx279133 TARGET_DEVICE_zte_zx279133_DEVICE_zte_zxslc-sr1010 \
  PACKAGE_kmod-zte-npu PACKAGE_kmod-zte-fnoffload PACKAGE_kmod-zte-rtl8372n \
  PACKAGE_luci-theme-footstrap; do
  grep -qx "CONFIG_${symbol}=y" .config || { echo "Missing required configuration: $symbol" >&2; exit 1; }
done
python3 - <<'PY'
import os, pathlib
def selections(path):
    return dict(line.split('=', 1) for line in pathlib.Path(path).read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)
requested = selections(pathlib.Path(os.environ['RUNNER_TEMP']) / 'sr1010-requested.config')
actual = selections('.config')
for name in ('autoreboot', 'mini-diskmanager', 'natmapt', 'partexp', 'upnp'):
    key = 'CONFIG_PACKAGE_luci-app-' + name
    if requested.get(key) in ('y', 'm') and actual.get(key) != requested[key]:
        raise SystemExit('Requested application was dropped: ' + key)
PY
mkdir -p "$GITHUB_WORKSPACE/sr1010-output"
cp .config "$GITHUB_WORKSPACE/sr1010-output/config.txt"
./scripts/diffconfig.sh > "$GITHUB_WORKSPACE/sr1010-output/diffconfig.txt"
{
  printf 'Firmware: '; git rev-parse HEAD
  printf 'CI: %s\n' "$GITHUB_SHA"
  printf 'Footstrap: '; git -C "$RUNNER_TEMP/sr1010-luci" rev-parse HEAD
  for repo in feeds/* package/luci-app-mini-diskmanager package/luci-app-partexp package/openwrt-natmapt package/openwrt-stuntman package/luci-app-natmapt; do
    if [ -d "$repo/.git" ]; then printf '%s: ' "$repo"; git -C "$repo" rev-parse HEAD; fi
  done
} > "$GITHUB_WORKSPACE/sr1010-output/sources.txt"
