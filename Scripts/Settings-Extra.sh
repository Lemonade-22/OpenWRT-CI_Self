#!/bin/bash
# Run in the OpenWrt source root, right after the upstream Settings.sh step.
#
# Additive only: everything here either appends to .config or runs a fixup the
# upstream script does not know about. Upstream logic is never rewritten, so it
# keeps flowing in through Scripts/Settings.sh.
set -eo pipefail

# Wi-Fi credentials are NOT touched here: upstream Settings.sh owns them and
# the tree already falls back to OWRT/12345678 in mac80211.uc. Re-adding a sed
# here only risks fighting whichever form upstream decides to use next.

#引入机型专用覆盖配置（在通用配置之后应用）
PROFILE_OVERRIDE="$GITHUB_WORKSPACE/Config/$WRT_CONFIG-EXTRA.txt"
if [ -f "$PROFILE_OVERRIDE" ]; then
  echo "Applying profile overrides from $PROFILE_OVERRIDE..."
  cat "$PROFILE_OVERRIDE" >> ./.config
fi

# ramips 6.18: generic RTL837x changes the context of the Ralink DSA patch.
if [ "$WRT_TARGET" = "ramips" ]; then
  python3 "$GITHUB_WORKSPACE/Scripts/Fix-Ramips-DSA.py" || exit $?
fi

# Keep LuCI's packaged default in sync with the theme selected for the image.
# A saved config from an older image may still point at a theme that is absent.
LUCI_DEFAULT_CONFIG='./feeds/luci/modules/luci-base/root/etc/config/luci'
if [ "$WRT_THEME" != 'bootstrap' ]; then
  if [ ! -f "$LUCI_DEFAULT_CONFIG" ]; then
    echo "::error::LuCI default config not found: $LUCI_DEFAULT_CONFIG"
    exit 1
  fi

  sed -i "s|/luci-static/bootstrap|/luci-static/$WRT_THEME|" "$LUCI_DEFAULT_CONFIG"
  if ! grep -Fq "option mediaurlbase '/luci-static/$WRT_THEME'" "$LUCI_DEFAULT_CONFIG"; then
    echo "::error::Failed to set LuCI's default theme to $WRT_THEME"
    exit 1
  fi

  THEME_DEFAULTS='./package/base-files/files/etc/uci-defaults/99_ci_luci_theme'
  mkdir -p "$(dirname "$THEME_DEFAULTS")"
  cat > "$THEME_DEFAULTS" <<'EOF'
#!/bin/sh
selected="$(uci -q get luci.main.mediaurlbase)"
[ "$selected" = '/luci-static/bootstrap' ] || exit 0
[ ! -e /usr/share/ucode/luci/template/themes/bootstrap/header.ut ] || exit 0
[ ! -e /usr/lib/lua/luci/view/themes/bootstrap/header.htm ] || exit 0
[ -f /usr/share/ucode/luci/template/themes/__WRT_THEME__/header.ut ] || exit 1
uci set luci.main.mediaurlbase='/luci-static/__WRT_THEME__'
uci commit luci
EOF
  sed -i "s|__WRT_THEME__|$WRT_THEME|g" "$THEME_DEFAULTS"
  chmod +x "$THEME_DEFAULTS"
fi
