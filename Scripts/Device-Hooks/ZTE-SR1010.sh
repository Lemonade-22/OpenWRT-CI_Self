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
# WOL 来自 VIKINGYFY/packages（luci-app-wolultra），以目录拷贝方式注入，不加 feed。
# homeproxy/sing-box 已移除（不再注入、不再选中）。
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
		package/network/services/mcfast \
		package/kernel/linux/modules

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

	# 1b) kmod-zte-npu / kmod-zte-fnoffload / kmod-zte-rtl8372n 定义在
	# package/kernel/linux/modules/zte.mk，不在 target/linux/zte 里。不拷它，
	# sr1010.mk 的 DEVICE_PACKAGES 就会在 target/install 阶段被 apk 判为
	# "no such package"，编译停在 target/linux failed to build。
	mkdir -p "$source_root/package/kernel/linux/modules"
	rm -f "$source_root/package/kernel/linux/modules/zte.mk"
	cp -a "$CNJN_TMP/package/kernel/linux/modules/zte.mk" \
		"$source_root/package/kernel/linux/modules/zte.mk"

	# 2) 内核切到 6.18 fork 模式
	sed -i 's/^KERNEL_PATCHVER:=7.3$/KERNEL_PATCHVER:=6.18/' "$source_root/target/linux/zte/Makefile"
	rm -rf "$source_root/target/linux/zte/patches-7.3"
	# 只删 $(error 行；残留的 ifneq/endif 变成无害空壳
	sed -i '/The ZTE target uses its Linux/d' "$source_root/target/linux/zte/Makefile"

	# 2b) 内核版本串：APK 包的 version 字段必须以数字开头（且不含大写），
	# 而外部内核树模式下 OpenWrt 用 URI 派生出 github_com_lemonade_22_...
	# 这种字母开头的串，任何内核模块打包都会 Error 99。改为读 fork 源码里
	# 的真实版本（6.18.60），既合法又诚实。
	KVER="$(curl -fsSL --retry 3 --max-time 60 \
		"https://raw.githubusercontent.com/Lemonade-22/linux-mainline-zte-zxslc-sr1010/build-6.18.60/Makefile" \
		| awk '/^VERSION =/{v=$3} /^PATCHLEVEL =/{p=$3} /^SUBLEVEL =/{s=$3} END{if(v&&p&&s) print v"."p"."s}')"
	case "$KVER" in
		[0-9]*.[0-9]*.[0-9]*) ;;
		*) echo "::error::could not read kernel version from fork (got '$KVER')" >&2; exit 1 ;;
	esac
	echo "Kernel version from fork: $KVER"
	python3 - "$source_root/include/kernel-version.mk" "$KVER" <<'PYVER'
import sys
p, kver = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
uri_line = "  LINUX_VERSION:=$(call sanitize_uri,$(call remove_uri_prefix,$(CONFIG_KERNEL_GIT_CLONE_URI)))"
ref_line = "  LINUX_VERSION:=$(LINUX_VERSION)-$(call sanitize_uri,$(CONFIG_KERNEL_GIT_REF))"
if uri_line not in s:
    raise SystemExit("::error::kernel-version.mk layout changed; cannot pin LINUX_VERSION")
s = s.replace(uri_line, "  LINUX_VERSION:=" + kver)
s = s.replace(ref_line + "\n", "")
open(p, "w", encoding="utf-8", newline="").write(s)
print("kernel-version.mk: LINUX_VERSION pinned to " + kver)
PYVER

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

	# 3c) ksmbd：6.18 的 SMB_SERVER select CRYPTO_LIB_ARC4，ksmbd.ko 因此引用
	# lib/crypto/libarc4.ko；而 fs.mk 里 KernelPackage/fs-ksmbd 的 DEPENDS 没写
	# kmod-crypto-arc4，libarc4.ko 就成了无主模块，打包时必然报
	#   Package kmod-fs-ksmbd is missing dependencies ... libarc4.ko
	# crypto.mk 的 KernelPackage/crypto-arc4 同时收 arc4.ko 与 libarc4.ko，
	# 补进 DEPENDS 即可（OpenWrt 的缺依赖检查只读 DEPENDS 包的 .provides）。
	# 注：6.18 里该 Kconfig 符号是 CONFIG_SMB_SERVER（不是 CONFIG_KSMBD），
	# 由 kmod 的 KCONFIG 带出，config-6.18 不必追加——追加了反而是无效符号。
	ksmbd_fs_mk="$source_root/package/kernel/linux/modules/fs.mk"
	if ! grep -q 'kmod-crypto-arc4' "$ksmbd_fs_mk"; then
		python3 - "$ksmbd_fs_mk" <<'PYKSMBD'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
head = "define KernelPackage/fs-ksmbd\n"
start = s.find(head)
if start < 0:
    raise SystemExit("::error::fs-ksmbd block not found in fs.mk")
end = s.find("\nendef", start)
if end < 0:
    raise SystemExit("::error::fs-ksmbd block has no endef")
block = s[start:end]
old = "\t  +kmod-fs-smbfs-common\n"
if old not in block:
    raise SystemExit("::error::fs-ksmbd DEPENDS layout changed; cannot add kmod-crypto-arc4")
block = block.replace(old, "\t  +kmod-fs-smbfs-common \\\n\t  +kmod-crypto-arc4\n", 1)
open(p, "w", encoding="utf-8", newline="").write(s[:start] + block + s[end:])
print("fs.mk: kmod-fs-ksmbd DEPENDS += kmod-crypto-arc4 (ships libarc4.ko)")
PYKSMBD
	fi

	# 3d) libarc4：kmod-mppe / kmod-fs-ksmbd 打包时报缺 libarc4.ko。
	# 6.18 的 PPP_MPPE 与 SMB_SERVER 都 select CRYPTO_LIB_ARC4，libarc4 于是编成
	# lib/crypto/libarc4.ko 这个无主模块；OpenWrt 的缺依赖检查只读 DEPENDS 包的
	# .provides，缺哪个 .ko 就报哪个，逐个包往 DEPENDS 里补不现实（mppe、ksmbd
	# 以及后续任何 select 它的包都得补一遍）。内建后不再产生 .ko，从根上消失。
	if ! grep -q '^CONFIG_CRYPTO_LIB_ARC4=y$' "$source_root/target/linux/zte/zx279133/config-6.18"; then
		cat >> "$source_root/target/linux/zte/zx279133/config-6.18" <<'ARC4'

# libarc4 built-in: kmod-mppe / kmod-fs-ksmbd packaging misses libarc4.ko
CONFIG_CRYPTO_LIB_ARC4=y
CONFIG_CRYPTO_ARC4=y
ARC4
	fi

	# 3e) bpf-headers 会把 target/linux/generic/{backport,pending,hack}-6.18 的补丁
	# 打到官方内核源码上以生成 eBPF 头文件；但真实内核是外部 cnjn 树，不走这些补丁。
	# 762（MxL862xx DSA tag）在 6.18.60 上两个 hunk 全部失败，直接删掉：
	# 它只影响头文件生成，不影响固件内核与 DSA 驱动。
	find "$source_root/target/linux/generic" -maxdepth 2 -name '762-v7.0-net-dsa-add-tag-format-for-MxL862xx-switches.patch' -delete 2>/dev/null || true
	# 3g) 三个 zte kmod 在 6.18.60 fork 上无实体文件可打：config-6.18 里
	# CONFIG_ZTE_ZX279133_ETH / CONFIG_ZTE_ZX279133_RTL8372N 都是 =y（内建，不产出
	# .ko），LAN_CONDUIT 是 bool（同理无 .ko），FNOFFLOAD 符号在 fork 里已消失。
	# 因此 npu.ko / fnoffload.ko / zx279133-rtl8372n.ko 都不存在，apk mkpkg 会报
	# "module ... is missing"，编译停在 package/kernel/linux failed to build。
	# NPU offload 功能由内核内建部分承担，MODPARAMS.npu 的运行时开关随之失效。
	# image/Makefile 由 cnjn 树整份覆盖，必须在本段（拷贝之后）删包。
	if [ -f "$source_root/target/linux/zte/image/Makefile" ]; then
		python3 - "$source_root/target/linux/zte/image/Makefile" <<'PYZTE'
import sys
pkgs = {'kmod-zte-npu', 'kmod-zte-fnoffload', 'kmod-zte-rtl8372n'}
p = sys.argv[1]
lines = open(p, encoding='utf-8').read().split('\n')
out = []
for ln in lines:
    toks = ln.strip().split()
    cont = bool(toks) and toks[-1] == '\\'
    core = [t for t in toks if t != '\\']
    if core and cont and all(t in pkgs for t in core):
        continue
    out.append(ln)
open(p, 'w', encoding='utf-8').write('\n'.join(out))
PYZTE
	fi

	# 4) VIKINGYFY/packages：wolultra，目录直拷（homeproxy、sing-box 已移除）
	rm -rf "$VIKY_TMP"
	git clone --depth=1 "$VIKY_PACKAGES" "$VIKY_TMP"
	for p in luci-app-wolultra; do
		[ -d "$VIKY_TMP/$p" ] || { echo "::error::$p missing in VIKINGYFY/packages" >&2; exit 1; }
		rm -rf "$source_root/package/$p"
		cp -a "$VIKY_TMP/$p" "$source_root/package/$p"
	done

	# 注：luci-app-static-gw 由 Scripts/Static-Gateway.sh 负责（clone + 强制选中），
	# 这里不再重复，否则 git clone 目标已存在会直接失败。

	# 4c) gpio-button-hotplug：内核 6.18 移除了 broadcast_uevent 与
	# uevent_next_seqnum（按键事件原本走 netlink skb 广播），该包编译必失败。
	# 补丁改为标准 kobject_uevent_env 路径，功能等价（仅少 SEQNUM 变量）。
	gpio_patch="$ci_root/Custom/patches/gpio-button-hotplug-6.18-uevent.patch"
	if [ -f "$gpio_patch" ]; then
		( cd "$source_root" && patch -p1 --forward --silent < "$gpio_patch" ) || \
			echo "::warning::gpio-button-hotplug uevent patch not applied (already patched?)" >&2
	fi

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

	# homeproxy/sing-box 本设备不装。Config/GENERAL.txt 是所有设备共用、且在设备配置
	# 之后拼接，里面仍写着 CONFIG_PACKAGE_luci-app-homeproxy=y，会把它带回来；
	# 这里在 defconfig 之前改成显式 not set。两者不被任何包 select，defconfig 不会重开。
	sed -i \
		-e 's/^CONFIG_PACKAGE_luci-app-homeproxy=y$/# CONFIG_PACKAGE_luci-app-homeproxy is not set/' \
		-e 's/^CONFIG_PACKAGE_sing-box=y$/# CONFIG_PACKAGE_sing-box is not set/' \
		"$source_root/.config"

	# kmod-ovpn-backports：GENERAL.txt 默认开的 7.3 驱动回移包，在 6.18 外部内核树上
	# 编译失败（MODULE_VERSION(OVPN_MODULE_VERSION) 未定义）。它只被带 DCO 的 openvpn
	# 变体依赖（feeds/packages/net/openvpn/Makefile），本设备一个 openvpn 包都没选，
	# 纯属无用，直接关掉。
	sed -i 's/^CONFIG_PACKAGE_kmod-ovpn-backports=y$/# CONFIG_PACKAGE_kmod-ovpn-backports is not set/' \
		"$source_root/.config"

	# kmod-mtd-rw：GENERAL.txt（第 35 行）默认开，但它是 2021 年的老模块，用内核私有
	# API，在 6.18 外部内核树上不可靠；而且它一旦被 defconfig 关掉、旧 apk 还留在索引里，
	# 新内核 hash 会与旧 apk 的 kernel= 依赖冲突，apk 直接报 Error 99。这里统一关掉。
	sed -i 's/^CONFIG_PACKAGE_kmod-mtd-rw=y$/# CONFIG_PACKAGE_kmod-mtd-rw is not set/' \
		"$source_root/.config"

	# samba4：GENERAL.txt（第 9 行 luci-app-samba4=y）把它整套带进来 —— samba4-libs
	# 8.55 MB + samba4-server 0.22 MB ≈ 8.8 MB。cnjn 原版固件的共享方案是 ksmbd
	# （ksmbd-server + kmod-fs-ksmbd + luci-app-ksmbd + wsdd2），两者都监听 445，功能
	# 完全重复；保持与上游一致并把 8.8 MB 还给 41 MiB 槽位，这里把 samba4 全系（含
	# luci 前端与 i18n）显式置为 not set。正则只认 samba4 开头的包名，ksmbd /
	# kmod-fs-ksmbd / luci-app-ksmbd / wsdd2 都不会被波及。
	sed -i -E \
		-e 's/^CONFIG_PACKAGE_(samba4[^=]*)=y$/# CONFIG_PACKAGE_\1 is not set/' \
		-e 's/^CONFIG_PACKAGE_(luci-(app|i18n)-samba4[^=]*)=y$/# CONFIG_PACKAGE_\1 is not set/' \
		"$source_root/.config"

	# 3g) 三个 zte kmod 在 6.18 fork 上无实体文件（见 prepare 的 3g），置 not set，
	# 防止 defconfig 或 build cache 把它们选回来。
	for pref in CONFIG_PACKAGE_ CONFIG_DEFAULT_; do
		for pkg in kmod-zte-npu kmod-zte-fnoffload kmod-zte-rtl8372n; do
			sed -i "s/^${pref}${pkg}=y$/# ${pref}${pkg} is not set/" "$source_root/.config" 2>/dev/null || true
		done
	done
}

verify() {
	# 防退化：明确不该出现的包
	for bad in CONFIG_PACKAGE_dae CONFIG_PACKAGE_luci-app-dae \
		CONFIG_PACKAGE_zerotier CONFIG_PACKAGE_luci-app-zerotier \
		CONFIG_PACKAGE_luci-theme-argon CONFIG_PACKAGE_luci-app-argon-config \
		CONFIG_PACKAGE_luci-theme-design CONFIG_PACKAGE_luci-theme-aerowert \
		CONFIG_PACKAGE_luci-app-homeproxy CONFIG_PACKAGE_sing-box \
		CONFIG_PACKAGE_kmod-ovpn-backports \
		CONFIG_PACKAGE_samba4 CONFIG_PACKAGE_samba4-server \
		CONFIG_PACKAGE_samba4-libs CONFIG_PACKAGE_luci-app-samba4 \
		CONFIG_PACKAGE_kmod-zte-npu CONFIG_PACKAGE_kmod-zte-fnoffload \
		CONFIG_PACKAGE_kmod-zte-rtl8372n; do
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
