#!/bin/bash
# ZTE SR1010 (中兴星云MAX, ZX279133)。
#
# 设备层来自 cnjn/immortalwrt（zte target：DTS、mkfw 打包、固件槽切换、Plugin 分区
# overlay、NPU/交换芯片固件），底树是 VIKINGYFY/immortalwrt @ owrt（6.18 内核、owrt 系统层）。
#
# 内核不走 cnjn 当前的 7.3 patch 系列（39 个补丁、显式禁止外部内核树），而是走
# cnjn 的 6.18 fork（linux-mainline-zte-zxslc-sr1010，ZX279133 全套支持原生在树里）：
# 因此本钩子在注入后要 1) 把 KERNEL_PATCHVER 改回 6.18；2) 删掉 patches-7.3；
# 3) 删掉 Makefile 里"禁止外部内核树"的 $(error；4) 补回 6.18 时代的 config-6.18。
#
# 代理与 WOL 来自 VIKINGYFY/packages（luci-app-homeproxy + sing-box、luci-app-wolultra），
# 以目录拷贝方式注入，不加 feed。
#
# zte-mesh 是独立 feed（cnjn/zte-mesh.git），在 prepare 追加到 feeds.conf.default，
# 时序上 prepare(L153) 早于 feeds update(L187) 和 make defconfig(L217)。
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_root="$(pwd)"

# cnjn 仓库里 6.18 时代的提交：config-6.18 从这里取。
CNJN_GIT="https://github.com/cnjn/immortalwrt.git"
CNJN_SPARSE_COMMIT="bbda4f1c8"
CNJN_KERNEL_FORK="https://github.com/Lemonade-22/linux-mainline-zte-zxslc-sr1010.git"
VIKY_PACKAGES="https://github.com/VIKINGYFY/packages.git"
CNJN_TMP="${TMPDIR:-/tmp}/cnjn-immortalwrt-zte"
VIKY_TMP="${TMPDIR:-/tmp}/vikingyfy-packages"
STATIC_GW_REPO="https://github.com/Lemonade-22/luci-app-static-gw.git"
STATIC_GW_TMP="${TMPDIR:-/tmp}/luci-app-static-gw"

case "${WRT_CONFIG:-}" in
	ZTE-SR1010) ;;
	*)
		echo "::error::ZTE SR1010 hook invoked for the wrong configuration" >&2
		exit 2
		;;
esac

prepare() {
	[ "${WRT_SOURCE:-}" = "VIKINGYFY/immortalwrt" ] || {
		echo "::error::SR1010 builds the owrt tree (VIKINGYFY/immortalwrt)" >&2; exit 1; }
	case "${WRT_BRANCH:-}" in
		owrt) ;;
		*)
			echo "::error::unsupported branch ${WRT_BRANCH:-} for SR1010" >&2; exit 1 ;;
	esac
	[ -d "$source_root/target/linux" ] || {
		echo "::error::$source_root does not look like an OpenWrt tree" >&2; exit 1; }

	# 1) cnjn 树：zte target + NPU/uboot 固件 + fxfall 自有包（flowproxy 等）
	rm -rf "$CNJN_TMP"
	git clone --depth=1 --filter=blob:none --sparse "$CNJN_GIT" "$CNJN_TMP"
	git -C "$CNJN_TMP" sparse-checkout set \
		target/linux/zte \
		package/firmware/zte \
		package/fxfall \
		package/utils/zte-fwslot \
		package/utils/luci-app-zte-fwslot \
		package/utils/fwupdate \
		package/utils/luci-app-fwupdate \
		package/network/services/mcfast

	# cp -a 源 目标：目标已存在时会把源“塞进”目标里形成嵌套目录，
	# 必须先清场保证幂等（第二次 CI 运行同样适用）
	rm -rf "$source_root/target/linux/zte"
	cp -a "$CNJN_TMP/target/linux/zte" "$source_root/target/linux/zte"
	mkdir -p "$source_root/package/firmware"
	rm -rf "$source_root/package/firmware/zte"
	cp -a "$CNJN_TMP/package/firmware/zte" "$source_root/package/firmware/zte"
	rm -rf "$source_root/package/fxfall"
	cp -a "$CNJN_TMP/package/fxfall" "$source_root/package/fxfall"
	# ZTE 专属功能包（注意：只拷特定目录，整树拷会把 cnjn 的通用包
	# 覆盖到 owrt 底树上，造成版本错乱）
	for p in utils/zte-fwslot utils/luci-app-zte-fwslot \
		utils/fwupdate utils/luci-app-fwupdate \
		network/services/mcfast; do
		[ -d "$CNJN_TMP/package/$p" ] || { echo "::error::$p missing in cnjn tree" >&2; exit 1; }
		rm -rf "$source_root/package/$p"
		cp -a "$CNJN_TMP/package/$p" "$source_root/package/$p"
	done

	# 2) 内核切到 6.18 fork 模式
	sed -i 's/^KERNEL_PATCHVER:=7.3$/KERNEL_PATCHVER:=6.18/' "$source_root/target/linux/zte/Makefile"
	rm -rf "$source_root/target/linux/zte/patches-7.3"
	# 只删 $(error 行；残留的 ifneq/endif 变成无害空壳
	sed -i '/The ZTE target uses its Linux/d' "$source_root/target/linux/zte/Makefile"

	# 2b) 内核版本串小写化：APK 包格式的 version 字段不接受大写字母，而
	# sanitize_uri 只替换符号不转大小写——fork 属于 Lemonade-22，会拼出
	# github_com_Lemonade_22_... 这样的非法版本，导致所有内核模块打包失败。
	python3 - "$source_root/include/kernel-version.mk" <<'PYLOWER'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
old = "sanitize_uri=$(call qstrip,$(subst @,_,$(subst :,_,$(subst .,_,$(subst -,_,$(subst /,_,$(1)))))))"
new = "sanitize_uri=$(call qstrip,$(shell echo $(subst @,_,$(subst :,_,$(subst .,_,$(subst -,_,$(subst /,_,$(1)))))) | tr A-Z a-z))"
if old in s:
    open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new))
    print("kernel-version.mk: sanitize_uri lowercased")
else:
    print("::warning::sanitize_uri pattern not found (already patched?)")
PYLOWER

	# 3) config-6.18：7.3 化的树里可能只剩 config-7.3，6.18 时代配置从钉死的提交取
	if [ ! -f "$source_root/target/linux/zte/zx279133/config-6.18" ]; then
		curl -fsSL --retry 3 --max-time 60 \
			"https://raw.githubusercontent.com/cnjn/immortalwrt/$CNJN_SPARSE_COMMIT/target/linux/zte/zx279133/config-6.18" \
			-o "$source_root/target/linux/zte/zx279133/config-6.18"
	fi
	[ -f "$source_root/target/linux/zte/zx279133/config-6.18" ] || {
		echo "::error::config-6.18 unavailable for the zte target" >&2; exit 1; }

	# 3b) COMPAT：zte-mesh 要在沙箱里执行厂商的 32 位 ARM multiapd。
	# cnjn 现役 config-7.3 带这组符号（原生执行），config-6.18 是老版没带，
	# 这里对齐补上；缺了它 zte-mesh 只能退 qemu-arm-static 手工方案。
	if ! grep -q '^CONFIG_COMPAT=y$' "$source_root/target/linux/zte/zx279133/config-6.18"; then
		cat >> "$source_root/target/linux/zte/zx279133/config-6.18" <<'COMPAT'

# 32-bit ARM userspace (vendor multiapd in zte-mesh sandbox); mirrors config-7.3
CONFIG_COMPAT=y
CONFIG_COMPAT_OLD_SIGACTION=y
CONFIG_COMPAT_32BIT_TIME=y
CONFIG_COMPAT_BINFMT_ELF=y
COMPAT
	fi

	# 4) VIKINGYFY/packages：homeproxy(+sing-box) 与 wolultra，目录直拷
	rm -rf "$VIKY_TMP"
	git clone --depth=1 "$VIKY_PACKAGES" "$VIKY_TMP"
	for p in luci-app-homeproxy sing-box luci-app-wolultra gecoosac luci-app-gecoosac; do
		[ -d "$VIKY_TMP/$p" ] || { echo "::error::$p missing in VIKINGYFY/packages" >&2; exit 1; }
		rm -rf "$source_root/package/$p"
		cp -a "$VIKY_TMP/$p" "$source_root/package/$p"
	done

	# 4b) luci-app-static-gw：按主机绑网关/DNS，自有仓库，根目录即包
	rm -rf "$STATIC_GW_TMP"
	git clone --depth=1 "$STATIC_GW_REPO" "$STATIC_GW_TMP"
	[ -f "$STATIC_GW_TMP/Makefile" ] || { echo "::error::static-gw missing Makefile" >&2; exit 1; }
	rm -rf "$source_root/package/luci-app-static-gw"
	cp -a "$STATIC_GW_TMP" "$source_root/package/luci-app-static-gw"
	rm -rf "$source_root/package/luci-app-static-gw/.git"

	# 5) zte-mesh feed：cnjn 的种子从它取 zte-mesh / luci-app-zte-mesh
	if ! grep -q "zte_mesh" "$source_root/feeds.conf.default" 2>/dev/null; then
		echo 'src-git zte_mesh https://github.com/cnjn/zte-mesh.git' >> "$source_root/feeds.conf.default"
	fi

	# 6) 默认主题：cnjn 的 base-files 可能带 99-zx279133-theme（指向被我们删掉的
	#    design/argon 主题），会盖掉 WRT_THEME 的 footstrap，删之。
	find "$source_root/target/linux/zte" "$source_root/package/fxfall" \
		-type f -name '99-zx279133-theme' -delete 2>/dev/null || true

	echo "ZTE SR1010: zte target injected, kernel = cnjn fork (6.18), feeds updated."
}

lint() {
	command -v git >/dev/null || { echo "::error::git required" >&2; exit 1; }
	command -v python3 >/dev/null || { echo "::error::python3 required (mkfw packaging)" >&2; exit 1; }
}

configure() {
	# 种子已应用、defconfig 已跑过：确认 zte 目标与关键包都在
	grep -q '^CONFIG_TARGET_zte=y$' "$source_root/.config" || {
		echo "::error::zte target missing after defconfig" >&2; exit 1; }
	grep -q '^CONFIG_PACKAGE_luci-app-homeproxy=y$' "$source_root/.config" || {
		echo "::error::homeproxy dropped by defconfig" >&2; exit 1; }
}

verify() {
	# 防退化：明确不该出现的包
	for bad in CONFIG_PACKAGE_dae CONFIG_PACKAGE_luci-app-dae \
		CONFIG_PACKAGE_zerotier CONFIG_PACKAGE_luci-app-zerotier \
		CONFIG_PACKAGE_luci-theme-argon CONFIG_PACKAGE_luci-app-argon-config \
		CONFIG_PACKAGE_luci-theme-design CONFIG_PACKAGE_luci-theme-aerowert; do
		if grep -q "^$bad" "$source_root/.config" 2>/dev/null; then
			echo "::error::forbidden package selected: $bad" >&2; exit 1
		fi
	done
	grep -q '^CONFIG_PACKAGE_luci-app-wolultra=y$' "$source_root/.config" || {
		echo "::error::wolultra missing" >&2; exit 1; }
	grep -q '^CONFIG_PACKAGE_luci-theme-footstrap=y$' "$source_root/.config" || {
		echo "::error::footstrap theme missing" >&2; exit 1; }
	grep -q '^CONFIG_PACKAGE_zte-fwslot=y$' "$source_root/.config" || {
		echo "::error::zte-fwslot missing" >&2; exit 1; }

	# mtd-rw：2021 年的老模块，用内核私有 API，在 6.18 外部内核树上编译失败；
	# 本固件无任何包依赖它。build cache 恢复可能带回旧的 =y 残留，这里强制清掉。
	if grep -q '^CONFIG_PACKAGE_kmod-mtd-rw=y$' "$source_root/.config"; then
		echo "::warning::kmod-mtd-rw re-enabled by cache/defconfig; forcing off" >&2
		sed -i 's/^CONFIG_PACKAGE_kmod-mtd-rw=y$/# CONFIG_PACKAGE_kmod-mtd-rw is not set/' "$source_root/.config"
	fi
}

verify-image() {
	# 41MB 槽位：镜像超限 mkfw 会自己报错，这里做一层宽度提醒
	local img
	img="$(find "$source_root/bin/targets" -type f \( -name '*sr1010*squashfs*' -o -name '*sr1010*factory*' \) 2>/dev/null | head -1 || true)"
	[ -n "$img" ] || { echo "::error::no SR1010 image produced" >&2; exit 1; }
	local size
	size="$(stat -c%s "$img")"
	echo "SR1010 image: $img ($size bytes)"
	# SLOT_SIZE = 0x2900000 = 42991616 (mkfw.py 硬编码的槽位大小)
	if [ "$size" -gt 42991616 ]; then
		echo "::warning::image exceeds the 41 MiB slot (0x2900000) — vendor U-Boot will reject it" >&2
		exit 1
	fi
}

package() {
	# 产物已由核心 workflow 收集，无需额外动作
	:
}

case "${1:-}" in
	prepare|lint|configure|verify|verify-image|package) "$1" ;;
	*)
		echo "::error::unknown phase: ${1:-}" >&2
		exit 2
		;;
esac
