# AP8220 1 GiB NAND / transition setup compatibility

## Status

An isolated AP8220 1 GiB test build is implemented. The patch applies to the inspected VIKINGYFY main and owrt sources. This opt-in variant builds owrt and is published only as a prerelease; a successful device boot has not yet been demonstrated.

The transition firmware's `setup` script is treated as immutable. Its Linux partition labels and the labels in the new system do not have to be identical: the physical offsets must match, while the installed system must also match the saved U-Boot boot arguments.

## Problem

An AP8220 sysupgrade image built by this repository from `VIKINGYFY/immortalwrt:main` does not boot after being installed through the existing transition firmware/setup flow.

The CI path is:

- `.github/workflows/QCA-ALL.yml`
- source: `VIKINGYFY/immortalwrt`
- branch: `main`
- original config: `IPQ807X-WIFI-{YES,NO}`; isolated test config: `IPQ807X-AP8220-1G-WIFI-NO`
- device: `CONFIG_TARGET_DEVICE_qualcommax_ipq807x_DEVICE_aliyun_ap8220=y`

## Evidence collected from the actual images

### Transition firmware DTB

The transition firmware FIT used on the 1 GiB NAND AP8220 describes NAND using fixed partitions:

- `rootfs`: offset `0x00000000`, size `0x3e800000` (1000 MiB)
- `ubi_kernel`: offset `0x3e800000`, size `0x01800000` (24 MiB)

Total: `0x40000000` (1 GiB).

Conceptually:

```
0x00000000                           0x3e800000       0x40000000
|------------- rootfs 1000 MiB ------------|-- ubi_kernel 24 MiB --|
```

### Immutable transition `setup` behavior

The observed setup flow attaches MTD1 as UBI, recreates volume 0 named `kernel` at 16 MiB, extracts the OpenWrt sysupgrade tar, and writes:

```
sysupgrade-aliyun_ap8220/kernel
```

into `/dev/ubi0_0`.

Therefore the setup environment expects, at minimum:

- MTD1 to be the 24 MiB `ubi_kernel` partition;
- UBI volume 0 to be named `kernel`;
- the sysupgrade archive to contain `sysupgrade-aliyun_ap8220/kernel`;
- the kernel payload to fit within the recreated 16 MiB volume.

### Failing VIKINGYFY image

The tested failing image was built from VIKINGYFY main on 2026-09-27.

Its sysupgrade archive has the expected layout:

```
sysupgrade-aliyun_ap8220/
├── CONTROL
├── kernel
└── root
```

The kernel is approximately 5.66 MiB, so the 16 MiB kernel UBI volume is not a size problem.

However, the DTB embedded in that kernel describes the NAND partition source using:

```dts
partitions {
    compatible = "qcom,smem-part";
};
```

It does **not** embed the transition firmware's explicit `rootfs` / `ubi_kernel` fixed-partition map.

This is a verified image difference. It is a strong boot-failure candidate, but it has **not yet been proven to be the only cause**.

## Additional boot/runtime findings from prior Codex analysis

The partition-layout mismatch is not the only known compatibility issue. The following observations are tracked alongside the fixed-partition implementation.

### 1. Partition-name / bootargs mismatch

In one failing boot, the VIKINGYFY kernel exposed the 1 GiB partition as lowercase `qwrt` and the trailing 24 MiB partition as `rootfs`, while the original bootargs requested uppercase `QWRT`. This produced:

```
cannot open mtd QWRT
```

After changing the referenced name to lowercase `qwrt`, the kernel started scanning the large partition. That establishes a real name/case-sensitivity mismatch in that boot path.

The device's saved U-Boot `fsbootargs` use `ubi.mtd=QWRT`. The test kernel therefore labels the large fixed partition uppercase `QWRT`; the transition kernel can continue to call the same physical range `rootfs`. `root=/dev/ubiblock0_1` chooses a volume *after* `ubi.mtd` attaches an MTD partition, so it cannot by itself resolve a bad `ubi.mtd` name.

### 2. ECC read errors remain unresolved

After the bootargs/name change allowed scanning of the large partition, the later log showed repeated NAND `ECC error -74` read failures.

This demonstrates a separate read problem that still needs to be explained, but the available evidence is insufficient to conclude that Linux 6.18's NAND driver is incompatible with the hardware. The same upgrade attempt had already experienced write failures, so that damaged/incomplete flash state cannot independently validate the driver's ability to read a correctly written system.

Likewise, a warning that configured ECC strength of 4 bits / 512 bytes is weaker than the NAND chip's stated requirement should be retained as evidence, but **must not be treated as a proven root cause on its own**.

Codex should compare the transition kernel's NAND controller/ECC configuration and the VIKINGYFY kernel DT/driver configuration before attributing the failure to a kernel regression.

### 3. AP8220 image geometry is currently wrong upstream

Current `VIKINGYFY/immortalwrt:main` defines AP8220 in `target/linux/qualcommax/image/ipq807x.mk` with:

```make
BLOCKSIZE := 128k
PAGESIZE := 2048
```

The observed device geometry is 256 KiB eraseblocks and 4096-byte pages.

The isolated AP8220 image recipe now uses:

```make
BLOCKSIZE := 256k
PAGESIZE := 4096
```

However, this mismatch must **not** be presented as the sole explanation for the failed transition upgrade. The tested sysupgrade archive contains a FIT kernel plus a SquashFS `root` member, while the transition environment created/attached UBI using the actual device geometry. The practical effect of these Makefile geometry values depends on which build steps consume them for this AP8220 image path and must be traced before changing them blindly.

### 4. Subsequent sysupgrade path is also incompatible

Current upstream `target/linux/qualcommax/ipq807x/base-files/lib/upgrade/platform.sh` handles AP8220 as:

```sh
aliyun,ap8220|\\
zte,mf269-stock)
    CI_UBIPART="rootfs"
    nand_do_upgrade "$1"
    ;;
```

The transition Linux calls the large partition `rootfs`, while the installed test Linux calls the same physical range `QWRT` to match the saved U-Boot bootargs. Both call the trailing 24 MiB partition `ubi_kernel`. Therefore the generic single-`CI_UBIPART=rootfs` upgrade path is not sufficient for the installed system.

The AP8220 test variant now uses separate kernel and root/data partitions:

```sh
CI_KERN_UBIPART="ubi_kernel"
CI_ROOT_UBIPART="QWRT"
CI_DATA_UBIPART="QWRT"
CI_KERN_VOL_ID=0
CI_ROOTFS_VOL_ID=1
CI_DATA_VOL_ID=2
nand_do_upgrade "$1"
```

The optional volume-ID variables in the test patch make `nand.sh` recreate the IDs used by the working QWRT layout. The tar writer also stops when a UBI volume lookup or `ubiupdatevol` fails, instead of reporting false success. This still needs a build and a device upgrade test.

### Review implication

The working hypothesis is now a multi-layer compatibility problem rather than a DTB-only problem:

1. **DT/DTS:** make the installed Linux expose 1000 MiB `QWRT` and 24 MiB `ubi_kernel` at the transition firmware's physical offsets.
2. **Bootargs/root discovery:** remove the `QWRT` vs `qwrt`/wrong-label dependency and verify how the root filesystem is selected.
3. **NAND geometry/ECC:** verify 4096-byte pages, 256 KiB eraseblocks, ECC requirements, and transition-vs-VIKINGYFY NAND configuration.
4. **Image recipe:** determine where `PAGESIZE`/`BLOCKSIZE` affect this sysupgrade build and correct AP8220-specific values where appropriate.
5. **Runtime sysupgrade:** make future upgrades understand the split `ubi_kernel` + `rootfs` layout instead of assuming a single UBI partition named `rootfs`.

A successful first boot after a DTB change would not close items 3-5; those must still be validated before considering the adaptation complete.

## Proposed direction

Keep the transition firmware and `setup` unchanged.

Adapt the VIKINGYFY AP8220 build so its physical NAND layout agrees with the transition environment and its large-partition name agrees with the saved U-Boot `ubi.mtd=QWRT` argument.

The AP8220 test patch overrides the NAND partition description as follows:

```dts
partitions {
    compatible = "fixed-partitions";

    partition@0 {
        label = "QWRT";
        reg = <0x00000000 0x3e800000>;
    };

    partition@3e800000 {
        label = "ubi_kernel";
        reg = <0x3e800000 0x01800000>;
    };
};
```

The committed patch uses the current upstream source's `nand@0/partitions` node and one address/size cell, and disables any inherited controller-level partition node.

## Preferred CI implementation

Do not maintain a full fork of VIKINGYFY/immortalwrt solely for this experiment.

The repository-owned patch is:

```
patches/ap8220-1g-nand.patch
```

`WRT-CORE.yml` applies it after cloning upstream, only for the isolated `IPQ807X-AP8220-1G-WIFI-NO` config. The normal multi-device QCA builds retain the original upstream AP8220 image.

This variant suppresses the upstream combined `factory.ubi`, which does not describe the two separate UBI partitions used here. Release filenames include `-1g-` so they cannot be mistaken for the stock AP8220 build.

Select the `AP8220_1G` input on `QCA-ALL` to build only this variant from `VIKINGYFY/immortalwrt:owrt`. The config requests both sysupgrade and initramfs images; the latter is for a RAM-boot/read-only NAND test before any flash write.

## First installation from the existing transition system

The release includes `Install-AP8220-1G-From-Transition.sh` and `SHA256SUMS.txt`.
After the new initramfs has read the existing NAND without ECC errors, boot the original transition ITB through **救砖 → Initramfs 启动** and upload the installer and the matching `-1g-` sysupgrade archive to `/tmp`.

Run over SSH, replacing the archive name with its actual full filename:

```sh
sh /tmp/Install-AP8220-1G-From-Transition.sh /tmp/qualcommax-ipq807x-aliyun_ap8220-squashfs-sysupgrade-1g-VIKINGYFY-owrt-wifi-no-DATE.bin
```

This replaces both kernel and rootfs and **erases rootfs_data, including old settings**.
Do not run the old `setup` or click the old web continuation as additional steps: the installer performs both writes explicitly, with fixed volume IDs and payload readback hashes.
It does not alter the bootloader environment or automatically reboot. Keep the already working saved `fsbootargs` containing `ubi.mtd=QWRT rootfstype=squashfs`.
Only reboot after the installer reports successful readback; on any error, remain in the transition system and retain the complete log.

The installer requires the existing UBI containers created by the previous working QWRT installation. It stops if either container cannot attach, rather than reformatting it. This is not a blank-flash provisioning tool.

## Codex review tasks

1. Locate the exact current AP8220 DTS/DTSI in `VIKINGYFY/immortalwrt:main` and identify where `qcom,smem-part` is inherited or declared.
2. Locate the AP8220 device/image definition (likely under the qualcommax image recipes) and document how `kernel`, `root`, and sysupgrade metadata are generated.
3. Verify whether replacing/overriding the NAND partition node with the transition firmware's fixed map is sufficient for early boot and rootfs discovery.
4. The immutable `setup` writes only the kernel to the 24 MiB partition. The transition web continuation attempts to write `root` to the 1000 MiB partition, but the observed VIKINGYFY attempt failed because its volume lookup produced `/dev/`. Therefore the initial install needs a separately verified root-volume writer; changing the new kernel cannot repair that old transition script.
5. Check `fstab`, `mount_root`, UBI/ubiblock behavior, platform upgrade scripts, and any `PART_NAME`/rootfs assumptions for AP8220.
6. Verify ART/caldata and MAC-address lookup behavior under the fixed partition map. Do not regress Wi-Fi calibration or board identity.
7. Check bootloader expectations for the `ubi_kernel` UBI volume and FIT payload (volume name/id, load/entry addresses, DTB selection and compression).
8. Implement the smallest isolated patch possible and add CI-time assertions that inspect the generated AP8220 image.

## Suggested CI assertions

Before publishing an AP8220 test artifact, fail the job unless all of the following are true:

- sysupgrade tar contains `sysupgrade-aliyun_ap8220/kernel` and `root`;
- kernel payload is <= 16 MiB;
- embedded DTB reports `QWRT` at `0x0 / 0x3e800000`;
- embedded DTB reports `ubi_kernel` at `0x3e800000 / 0x01800000`;
- the AP8220 kernel DTB no longer relies on `qcom,smem-part` for this 1 GiB NAND variant.

`Scripts/Check-AP8220-1G.py` checks these FIT/DTB properties, the SquashFS member and the presence of an initramfs ITB before publishing an AP8220 test build.

## Validation sequence

1. Build only; do not flash.
2. Extract the generated AP8220 sysupgrade archive.
3. Inspect the kernel FIT and embedded DTB.
4. Compare the generated DTB against the known-good transition firmware DTB.
5. Confirm kernel size and sysupgrade member paths.
6. RAM-boot the new initramfs and inspect the 1 GiB NAND/UBI read path for ECC errors without changing flash contents.
7. Use `Scripts/Install-AP8220-1G-From-Transition.sh` only with the published `-1g-` sysupgrade archive from the transition initramfs. It checks the actual MTD layout, writes kernel as small-UBI volume 0 and root as big-UBI volume 1, recreates data volume 2, and hashes the rootfs readback. It does not call `fw_setenv` because that transition image lacks `/etc/fw_env.config`. Confirm U-Boot's saved `fsbootargs` still contain `ubi.mtd=QWRT` before booting. This script has not yet been tested on the device.
8. Only after the read-only test and writer validation, perform a controlled flash test with serial recovery available.

## Non-goals

This proposal does not attempt to change:

- the immutable transition `setup` script;
- PPE/NSS acceleration selection;
- Ethernet topology;
- Wi-Fi enable/disable policy;
- unrelated IPQ807x devices.

The first experiment should minimize variables and address only AP8220 1 GiB NAND/setup compatibility.

## LiBwrt/LibWrt reference

The [LibWrt `25.12-nss` AP8220 DTS](https://github.com/LiBwrt/LibWrt/blob/25.12-nss/target/linux/qualcommax/files/arch/arm64/boot/dts/qcom/ipq8071-ap8220.dts) disables an inherited controller-level partition node and supplies `fixed-partitions` under `nand@0`. It also uses ECC 4/512 and `root=/dev/ubiblock0_1`. These are useful structural comparisons with the VIKINGYFY DTS. Its `reg = <0x0 0x0>` rootfs definition, 2048/128k image recipe and single-partition upgrade path are not the required 1 GiB/4096/256-KiB split. The observed `ECC error -74` remains unexplained until the new initramfs reads a known-good NAND image successfully.
