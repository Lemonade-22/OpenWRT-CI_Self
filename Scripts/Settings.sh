#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 VIKINGYFY

#移除luci-app-attendedsysupgrade
sed -i "/attendedsysupgrade/d" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改默认主题
sed -i "s/luci-theme-bootstrap/luci-theme-$WRT_THEME/g" $(find ./feeds/luci/collections/ -type f -name "Makefile")
#修改immortalwrt.lan关联IP
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $(find ./feeds/luci/modules/luci-mod-system/ -type f -name "flash.js")
#添加编译日期标识
sed -i "s/(\(luciversion || ''\))/(\1) + (' \/ $WRT_MARK-$WRT_DATE')/g" $(find ./feeds/luci/modules/luci-mod-status/ -type f -name "10_system.js")

WIFI_SH=$(find ./target/linux/{mediatek/filogic,qualcommax}/base-files/etc/uci-defaults/ -type f -name "*set-wireless.sh" 2>/dev/null)
WIFI_UC="./package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc"
if [ -f "$WIFI_SH" ]; then
	#修改WIFI名称
	sed -i "s/BASE_SSID='.*'/BASE_SSID='$WRT_SSID'/g" $WIFI_SH
	#修改WIFI密码
	sed -i "s/BASE_WORD='.*'/BASE_WORD='$WRT_WORD'/g" $WIFI_SH
elif [ -f "$WIFI_UC" ]; then
	#修改WIFI名称
	sed -i "s/ssid='.*'/ssid='$WRT_SSID'/g" $WIFI_UC
	sed -i "s/key='.*'/key='$WRT_WORD'/g" $WIFI_UC
fi

CFG_FILE="./package/base-files/files/bin/config_generate"
#修改默认IP地址
sed -i "s/192\.168\.[0-9]*\.[0-9]*/$WRT_IP/g" $CFG_FILE
#修改默认主机名
sed -i "s/hostname='.*'/hostname='$WRT_NAME'/g" $CFG_FILE

#配置文件修改
echo "CONFIG_PACKAGE_luci=y" >> ./.config
echo "CONFIG_LUCI_LANG_zh_Hans=y" >> ./.config
echo "CONFIG_PACKAGE_luci-theme-$WRT_THEME=y" >> ./.config
case "$WRT_THEME" in
	aurora|kucat)
		echo "CONFIG_PACKAGE_luci-app-$WRT_THEME-config=y" >> ./.config
		;;
esac

#引入私有扩展配置
if [ -f "$GITHUB_WORKSPACE/Config/PRIVATE.txt" ]; then
	echo "Applying private configurations from PRIVATE.txt..."
	cat $GITHUB_WORKSPACE/Config/PRIVATE.txt >> ./.config
fi

#引入机型专用覆盖配置（在通用配置之后应用）
PROFILE_OVERRIDE="$GITHUB_WORKSPACE/Config/$WRT_CONFIG-EXTRA.txt"
if [ -f "$PROFILE_OVERRIDE" ]; then
	echo "Applying profile overrides from $PROFILE_OVERRIDE..."
	cat "$PROFILE_OVERRIDE" >> ./.config
fi

#手动调整的插件
if [ -n "$WRT_PACKAGE" ]; then
	echo -e "$WRT_PACKAGE" >> ./.config
fi

#无WIFI配置标志
if [[ "${WRT_CONFIG,,}" == *"wifi"* && "${WRT_CONFIG,,}" == *"no"* ]]; then
	echo "WRT_WIFI=wifi-no" >> $GITHUB_ENV
fi

#高通平台调整
DTS_PATH="./target/linux/qualcommax/dts/"
if [[ "${WRT_TARGET^^}" == *"QUALCOMMAX"* && "${WRT_CONFIG:-}" != "ZN-M2-WIFI-NO" ]]; then
	#无WIFI配置调整Q6大小
	if [[ "${WRT_CONFIG,,}" == *"wifi"* && "${WRT_CONFIG,,}" == *"no"* ]]; then
		find $DTS_PATH -type f ! -iname '*nowifi*' -exec sed -i 's/ipq\(6018\|8074\).dtsi/ipq\1-nowifi.dtsi/g' {} +
		echo "qualcommax set up nowifi successfully!"
	fi
fi


# ramips 6.18: generic RTL837x changes the context of the Ralink DSA patch.
if [[ "${WRT_TARGET:-}" == "ramips" ]]; then
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
