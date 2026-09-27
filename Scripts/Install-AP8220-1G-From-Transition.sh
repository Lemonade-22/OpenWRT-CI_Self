#!/bin/sh
# Run only from the AP8220 1 GiB transition initramfs, with serial recovery available.
set -eu

die() {
	echo "AP8220 install stopped: $*" >&2
	exit 1
}

FW="${1:-}"
[ -n "$FW" ] || die "pass the published AP8220 1g sysupgrade filename as the argument"
[ -f "$FW" ] || die "sysupgrade archive not found: $FW"
case "$(basename "$FW")" in
	*aliyun_ap8220*1g*sysupgrade*.bin|*aliyun_ap8220*sysupgrade*1g*.bin) ;;
	*) die "this is not the named AP8220 1g sysupgrade test artifact" ;;
esac
grep -q '^mtd0: 3e800000 00040000 "rootfs"$' /proc/mtd || die "unexpected 1000 MiB MTD layout"
grep -q '^mtd1: 01800000 00040000 "ubi_kernel"$' /proc/mtd || die "unexpected 24 MiB MTD layout"
[ ! -e /sys/class/ubi/ubi0/mtd_num ] || die "UBI device 0 is already attached; inspect ubinfo -a first"

KERNEL=/tmp/ap8220-kernel.itb
ROOT=/tmp/ap8220-root.squashfs
tar -xOf "$FW" sysupgrade-aliyun_ap8220/kernel > "$KERNEL" || die "kernel member missing"
tar -xOf "$FW" sysupgrade-aliyun_ap8220/root > "$ROOT" || die "root member missing"
kernel_size="$(wc -c < "$KERNEL")"
root_size="$(wc -c < "$ROOT")"
[ "$kernel_size" -gt 0 ] && [ "$kernel_size" -le 16777216 ] || die "kernel does not fit 16 MiB UBI volume"
[ "$root_size" -gt 0 ] && [ "$root_size" -le 268435456 ] || die "unexpected rootfs size"
kernel_magic="$(dd if="$KERNEL" bs=4 count=1 2>/dev/null | hexdump -v -e '4/1 "%02x"')"
root_magic="$(dd if="$ROOT" bs=4 count=1 2>/dev/null | hexdump -v -e '4/1 "%02x"')"
[ "$kernel_magic" = d00dfeed ] || die "kernel is not a FIT image"
[ "$root_magic" = 68737173 ] || die "root is not a SquashFS image"

# Validate both existing UBI layouts before replacing either payload.
ubiattach -m 1 -b 1 || die "cannot attach ubi_kernel"
[ "$(cat /sys/class/ubi/ubi0/mtd_num)" = 1 ] || die "UBI device 0 is not mtd1"
if [ -e /sys/class/ubi/ubi0_0/name ]; then
	[ "$(cat /sys/class/ubi/ubi0_0/name)" = kernel ] || die "unexpected kernel volume 0"
fi
ubidetach -m 1 || die "cannot detach ubi_kernel"
ubiattach -m 0 || die "cannot attach big rootfs UBI; stop without formatting"
[ "$(cat /sys/class/ubi/ubi0/mtd_num)" = 0 ] || die "UBI device 0 is not mtd0"
for item in '0:kernel' '1:rootfs' '2:rootfs_data'; do
	id="${item%%:*}"
	name="${item#*:}"
	if [ -e "/sys/class/ubi/ubi0_${id}/name" ]; then
		[ "$(cat "/sys/class/ubi/ubi0_${id}/name")" = "$name" ] || die "unexpected UBI volume at ID $id"
	fi
done
ubidetach -m 0 || die "big rootfs UBI is busy"

echo "Replacing kernel, rootfs and rootfs_data; existing system settings will be erased."
echo "Writing $kernel_size-byte FIT to 24 MiB ubi_kernel..."
ubiattach -m 1 -b 1 || die "cannot attach ubi_kernel"
[ "$(cat /sys/class/ubi/ubi0/mtd_num)" = 1 ] || die "UBI device 0 is not mtd1"
if [ -e /sys/class/ubi/ubi0_0/name ]; then
	[ "$(cat /sys/class/ubi/ubi0_0/name)" = kernel ] || die "unexpected volume 0 in ubi_kernel"
	if [ -e /sys/class/block/ubiblock0_0 ]; then
		ubiblock -r /dev/ubi0_0 || die "kernel ubiblock is busy"
	fi
	ubirmvol /dev/ubi0 -N kernel || die "cannot remove old kernel volume"
fi
ubimkvol /dev/ubi0 -n 0 -N kernel -s 16MiB || die "cannot create kernel volume 0"
[ -c /dev/ubi0_0 ] || die "kernel volume character device missing"
ubiupdatevol /dev/ubi0_0 "$KERNEL" || die "kernel write failed"
expected="$(sha256sum "$KERNEL" | cut -d ' ' -f 1)"
actual="$(head -c "$kernel_size" /dev/ubi0_0 | sha256sum | cut -d ' ' -f 1)"
[ "$expected" = "$actual" ] || die "kernel readback hash differs from archive"
ubidetach -m 1 || die "cannot detach ubi_kernel"

echo "Writing $root_size-byte SquashFS to 1000 MiB rootfs..."
ubiattach -m 0 || die "cannot attach big rootfs UBI; stop, do not format it automatically"
[ "$(cat /sys/class/ubi/ubi0/mtd_num)" = 0 ] || die "UBI device 0 is not mtd0"
for item in '0:kernel' '1:rootfs' '2:rootfs_data'; do
	id="${item%%:*}"
	name="${item#*:}"
	if [ -e "/sys/class/ubi/ubi0_${id}/name" ]; then
		[ "$(cat "/sys/class/ubi/ubi0_${id}/name")" = "$name" ] || die "unexpected UBI volume at ID $id"
	fi
done
if [ -e /sys/class/ubi/ubi0_1/name ]; then
	if [ -e /sys/class/block/ubiblock0_1 ]; then
		ubiblock -r /dev/ubi0_1 || die "rootfs ubiblock is busy"
	fi
fi
if [ -e /sys/class/ubi/ubi0_2/name ]; then
	if [ -e /sys/class/block/ubiblock0_2 ]; then
		ubiblock -r /dev/ubi0_2 || die "rootfs_data ubiblock is busy"
	fi
	ubirmvol /dev/ubi0 -N rootfs_data || die "cannot remove old rootfs_data"
fi
if [ -e /sys/class/ubi/ubi0_1/name ]; then
	ubirmvol /dev/ubi0 -N rootfs || die "cannot remove old rootfs"
fi
ubimkvol /dev/ubi0 -n 1 -N rootfs -s "$root_size" || die "cannot create rootfs volume 1"
[ -c /dev/ubi0_1 ] || die "rootfs volume character device missing"
if [ -e /sys/class/block/ubiblock0_1 ]; then
	ubiblock -r /dev/ubi0_1 || die "new rootfs ubiblock is busy"
fi
ubiupdatevol /dev/ubi0_1 "$ROOT" || die "rootfs write failed"
ubimkvol /dev/ubi0 -n 2 -N rootfs_data -m || die "cannot create rootfs_data volume 2"

if [ ! -e /sys/class/block/ubiblock0_1 ]; then
	ubiblock -c /dev/ubi0_1 || die "cannot create rootfs readback block"
fi
expected="$(sha256sum "$ROOT" | cut -d ' ' -f 1)"
actual="$(head -c "$root_size" /dev/ubiblock0_1 | sha256sum | cut -d ' ' -f 1)"
[ "$expected" = "$actual" ] || die "rootfs readback hash differs from archive"
sync
echo "AP8220 image written and rootfs readback verified. Check U-Boot fsbootargs=ubi.mtd=QWRT before booting."
