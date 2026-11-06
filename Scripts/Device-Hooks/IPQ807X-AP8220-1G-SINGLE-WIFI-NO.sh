#!/bin/bash
# AP8220 1 GiB NAND —— 单分区（NAND 整片就是一个 rootfs）变体。
# 分区不再写死在内核 DTB 里，改由 MIBIB 经 qcom,smem-part 提供。
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_root="$(pwd)"
upload="$source_root/upload"
patch_file="$ci_root/patches/ap8220-1g-single-rootfs.patch"
dts_rel="target/linux/qualcommax/dts/ipq8071-ap8220.dts"

if [ "${WRT_CONFIG:-}" != "IPQ807X-AP8220-1G-SINGLE-WIFI-NO" ]; then
	echo "::error::AP8220 single-rootfs hook invoked for the wrong configuration" >&2
	exit 2
fi

case "${1:-}" in
	prepare)
		[ "${WRT_SOURCE:-}" = "VIKINGYFY/immortalwrt" ] || {
			echo "::error::AP8220 single-rootfs must build VIKINGYFY/immortalwrt" >&2; exit 1; }
		[ "${WRT_BRANCH:-}" = "owrt" ] || {
			echo "::error::the single-rootfs patch only tracks the owrt branch" >&2; exit 1; }
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
		;;
	verify)
		grep -Eq "^CONFIG_TARGET_DEVICE_qualcommax_ipq807x_DEVICE_aliyun_ap8220=y$" .config || {
			echo "::error::AP8220 device is not selected" >&2; exit 1; }
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
