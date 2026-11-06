#!/bin/bash
# AP8220 1 GiB NAND —— 单分区（NAND 整片就是一个 rootfs）变体。
# 分区不再写死在内核 DTB 里，改由 MIBIB 经 qcom,smem-part 提供。
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_root="$(pwd)"
upload="$source_root/upload"
patch_file="$ci_root/patches/ap8220-1g-single-rootfs.patch"
dts_rel="target/linux/qualcommax/dts/ipq8071-ap8220.dts"

# 同一硬件的 WIFI-YES / WIFI-NO 两个版本共用这套分区与产物逻辑，只有配置包里
# 是否关闭 ath11k 不同。
case "${WRT_CONFIG:-}" in
	IPQ807X-AP8220-1G-SINGLE-WIFI-NO|IPQ807X-AP8220-1G-SINGLE-WIFI-YES) ;;
	*)
		echo "::error::AP8220 single-rootfs hook invoked for the wrong configuration" >&2
		exit 2
		;;
esac

case "${1:-}" in
	prepare)
		[ "${WRT_SOURCE:-}" = "VIKINGYFY/immortalwrt" ] || {
			echo "::error::AP8220 single-rootfs must build VIKINGYFY/immortalwrt" >&2; exit 1; }
		case "${WRT_BRANCH:-}" in
			owrt|main) ;;
			*)
				echo "::error::unsupported branch ${WRT_BRANCH:-} for the AP8220 single-rootfs build" >&2
				exit 1 ;;
		esac
		git apply --check "$patch_file"
		git apply "$patch_file"
		git diff --check
		git diff --stat
		grep -q "compatible = \"qcom,smem-part\";" "$dts_rel" || {
			echo "::error::NAND partitions are not qcom,smem-part after patching" >&2; exit 1; }
		grep -q "nand-ecc-strength = <8>;" "$dts_rel" || {
			echo "::error::nand-ecc-strength is not 8/512 after patching" >&2; exit 1; }
		if grep -q "label = \"QWRT\"" "$dts_rel"; then
			echo "::error::fixed QWRT partition leaked into the single-rootfs build" >&2; exit 1
		fi
		;;
	lint)
		sh -n "$ci_root/Scripts/Device-Hooks/IPQ807X-AP8220-1G-SINGLE-WIFI-NO.sh"
		python3 -m py_compile "$ci_root/Scripts/Check-AP8220-1G-Single.py"
		;;
	configure)
		# WIFI-NO 完全沿用上游 Config/IPQ807X-WIFI-NO.txt 的行为，此处不额外裁剪。
		# 但必须产出 initramfs：ubiformat 整片 NAND 只能在内存系统里做，
		# 而且单分区布局下它是唯一的救砖入口。
		sed -i '/^CONFIG_TARGET_ROOTFS_INITRAMFS=/d; /^# CONFIG_TARGET_ROOTFS_INITRAMFS is not set$/d; /^CONFIG_TARGET_ROOTFS_SQUASHFS=/d; /^# CONFIG_TARGET_ROOTFS_SQUASHFS is not set$/d' .config
		printf '%s\n' 'CONFIG_TARGET_ROOTFS_INITRAMFS=y' 'CONFIG_TARGET_ROOTFS_SQUASHFS=y' >> .config
		;;
	verify)
		grep -Eq "^CONFIG_TARGET_DEVICE_qualcommax_ipq807x_DEVICE_aliyun_ap8220=y$" .config || {
			echo "::error::AP8220 device is not selected" >&2; exit 1; }
		grep -Eq "^CONFIG_TARGET_ROOTFS_INITRAMFS=y$" .config || {
			echo "::error::AP8220 initramfs output is not enabled" >&2; exit 1; }
		if [ "${WRT_BRANCH:-}" = "main" ]; then
			for pattern in \
				"^CONFIG_PACKAGE_nss-firmware=y$" \
				"^CONFIG_PACKAGE_kmod-qca-nss-drv=y$" \
				"^CONFIG_PACKAGE_kmod-qca-nss-ecm=y$" \
				"^CONFIG_PACKAGE_kmod-qca-nss-dp=y$" \
				"^CONFIG_PACKAGE_kmod-qca-ssdk=y$"
			do
				grep -Eq "$pattern" .config || {
					echo "::error::NSS is not selected ($pattern); 编译NSS固件 requires VIKINGYFY/immortalwrt main" >&2
					exit 1; }
			done
		fi
		;;
	verify-image)
		python3 "$ci_root/Scripts/Check-AP8220-1G-Single.py" "$source_root/bin/targets/qualcommax/ipq807x/"
		;;
	package)
		cd "$upload"
		for file in *aliyun_ap8220*; do
			[ -e "$file" ] || continue
			case "$file" in
				*single*) continue ;;
			esac
			mv -f -- "$file" "${file/aliyun_ap8220/aliyun_ap8220-single}"
		done
		rm -f SHA256SUMS.txt
		if command -v sha256sum >/dev/null 2>&1; then
			sha256sum -- * > SHA256SUMS.txt
		fi
		cat >> "$source_root/release-body.md" <<'EOF'

==== AP8220 1G 单分区版 ====

本版假设 NAND 的 MIBIB 已被改为「单个 rootfs 分区，覆盖整片 1 GiB」。
如果分区仍是 QWRT(1000 MiB) + ubi_kernel(24 MiB)，请不要刷这个包。

uboot 里直接刷：选用 *factory.ubi*（裸 UBI 镜像），不是 sysupgrade.bin。
sysupgrade.bin 只用于系统内部升级。

回滚：把 MIBIB 刷回双分区版本，并恢复 fsbootargs=ubi.mtd=QWRT。
EOF
		;;
	*)
		echo "Usage: $0 prepare|lint|configure|verify|verify-image|package" >&2
		exit 2
		;;
esac