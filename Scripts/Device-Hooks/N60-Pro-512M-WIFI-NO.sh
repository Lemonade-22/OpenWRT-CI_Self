#!/bin/bash
# Netcore N60 Pro 512M NAND。
#
# 出厂/上游设备树把 ubi 分区限在 122.5 MiB（0x7a80000），可这颗芯片有 512 MB NAND。
# patches/n60pro-512m-ubi-5065m.patch 把分区改成 0x1fa80000（约 506.5 MiB），
# 固件这才"认得"整片空间——否则 sysupgrade 只能写进 122.5 MiB。
#
# 本钩子由通用核心在 prepare/verify/verify-image 阶段调用，和 WIFI-YES/NO 无关：
# 两个版本共用同一套分区与产物逻辑。
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_root="$(pwd)"
patch_file="$ci_root/patches/n60pro-512m-ubi-5065m.patch"
dts_rel="target/linux/mediatek/dts/mt7986a-netcore-n60-pro.dts"
ubi_reg="0x1fa80000"

case "${WRT_CONFIG:-}" in
	N60-Pro-512M-WIFI-YES|N60-Pro-512M-WIFI-NO) ;;
	*)
		echo "::error::N60 Pro hook invoked for the wrong configuration" >&2
		exit 2
		;;
esac

case "${1:-}" in
	prepare)
		[ "${WRT_SOURCE:-}" = "VIKINGYFY/immortalwrt" ] || {
			echo "::error::N60 Pro must build VIKINGYFY/immortalwrt" >&2; exit 1; }
		case "${WRT_BRANCH:-}" in
			owrt|main) ;;
			*)
				echo "::error::unsupported branch ${WRT_BRANCH:-} for N60 Pro" >&2
				exit 1 ;;
		esac
		[ -f "$patch_file" ] || {
			echo "::error::missing $patch_file" >&2; exit 1; }
		git apply --check "$patch_file"
		git apply "$patch_file"
		git diff --check
		grep -q "reg = <0x0580000 $ubi_reg>;" "$dts_rel" || {
			echo "::error::ubi partition is not enlarged to 506.5 MiB after patching" >&2; exit 1; }
		echo "N60 Pro: ubi partition widened to $ubi_reg (about 506.5 MiB)"
		;;
	lint)
		sh -n "$ci_root/Scripts/Device-Hooks/N60-Pro-512M-WIFI-NO.sh"
		bash --version >/dev/null
		;;
	configure)
		# 上游 filogic 默认只出 sysupgrade.itb；这里不额外改产物格式，
		# 只保证 squashfs 根仍是打包对象（WIFI-YES/NO 都要）。
		sed -i '/^CONFIG_TARGET_ROOTFS_SQUASHFS=/d; /^# CONFIG_TARGET_ROOTFS_SQUASHFS is not set$/d' .config
		echo 'CONFIG_TARGET_ROOTFS_SQUASHFS=y' >> .config
		;;
	verify)
		grep -Eq '^CONFIG_TARGET_DEVICE_mediatek_filogic_DEVICE_netcore_n60-pro=y$' .config || {
			echo "::error::N60 Pro device is not selected" >&2; exit 1; }
		grep -Eq '^CONFIG_TARGET_ROOTFS_SQUASHFS=y$' .config || {
			echo "::error::N60 Pro squashfs rootfs is not enabled" >&2; exit 1; }
		# make defconfig 不会重写 dts，但补丁若被打回必须当场失败，不能等刷机。
		grep -q "reg = <0x0580000 $ubi_reg>;" "$dts_rel" || {
			echo "::error::ubi partition reverted to the stock 122.5 MiB" >&2; exit 1; }
		;;
	verify-image)
		img_dir="$source_root/bin/targets/mediatek/filogic"
		[ -d "$img_dir" ] || { echo "::error::no image directory at $img_dir" >&2; exit 1; }
		compgen -G "$img_dir/*netcore_n60-pro*sysupgrade*" >/dev/null || {
			echo "::error::no N60 Pro sysupgrade image was produced" >&2; exit 1; }
		size="$(stat -c %s "$img_dir"/*netcore_n60-pro*sysupgrade* | sort -n | tail -1)"
		limit=$((512 * 1024 * 1024))
		[ "$size" -lt "$limit" ] || {
			echo "::error::sysupgrade image is ${size} bytes, larger than the 512 MiB NAND" >&2; exit 1; }
		echo "N60 Pro: sysupgrade image $size bytes"
		;;
	package)
		;;
	*)
		echo "Usage: $0 prepare|lint|configure|verify|verify-image|package" >&2
		exit 2
		;;
esac
