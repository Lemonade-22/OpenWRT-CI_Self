# AP8220 1 GiB NAND / transition setup compatibility proposal

## Status

Design and validation proposal only. **Do not merge as an implementation without reviewing the upstream VIKINGYFY/immortalwrt AP8220 DTS, image recipe and upgrade path.**

The transition firmware's `setup` script is treated as an immutable compatibility contract.

## Problem

An AP8220 sysupgrade image built by this repository from `VIKINGYFY/immortalwrt:main` does not boot after being installed through the existing transition firmware/setup flow.

The CI path is:

- `.github/workflows/QCA-ALL.yml`
- source: `VIKINGYFY/immortalwrt`
- branch: `main`
- config: `IPQ807X-WIFI-{YES,NO}`
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

The partition-layout mismatch is not the only known compatibility issue. The following observations must be reviewed together with the fixed-partition proposal.

### 1. Partition-name / bootargs mismatch

In one failing boot, the VIKINGYFY kernel exposed the 1 GiB partition as lowercase `qwrt` and the trailing 24 MiB partition as `rootfs`, while the original bootargs requested uppercase `QWRT`. This produced:

```
cannot open mtd QWRT
```

After changing the referenced name to lowercase `qwrt`, the kernel started scanning the large partition. That establishes a real name/case-sensitivity mismatch in that boot path.

This does **not** by itself prove the final desired partition labels; the fixed-partition proposal should instead make the kernel-visible names deliberately match the immutable transition layout and any bootloader/rootfs expectations.

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

So the AP8220 image recipe should be reviewed for:

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

In the transition-compatible 1 GiB layout proposed here, `rootfs` is the large 1000 MiB partition and `ubi_kernel` is the separate 24 MiB kernel UBI partition. Therefore the generic single-`CI_UBIPART=rootfs` upgrade path is not sufficient to describe this split layout.

Codex should determine whether AP8220 needs the same split-UBI variables used elsewhere in the file, conceptually:

```sh
CI_KERN_UBIPART="ubi_kernel"
CI_ROOT_UBIPART="rootfs"
CI_DATA_UBIPART="rootfs"
nand_do_upgrade "$1"
```

This is a candidate direction, **not yet a validated patch**. It must be checked against `nand_do_upgrade` behavior, the actual rootfs format, volume names, bootloader expectations, and the immutable transition install path.

### Review implication

The working hypothesis is now a multi-layer compatibility problem rather than a DTB-only problem:

1. **DT/DTS:** make Linux expose the intended 1000 MiB `rootfs` and 24 MiB `ubi_kernel` partitions consistently.
2. **Bootargs/root discovery:** remove the `QWRT` vs `qwrt`/wrong-label dependency and verify how the root filesystem is selected.
3. **NAND geometry/ECC:** verify 4096-byte pages, 256 KiB eraseblocks, ECC requirements, and transition-vs-VIKINGYFY NAND configuration.
4. **Image recipe:** determine where `PAGESIZE`/`BLOCKSIZE` affect this sysupgrade build and correct AP8220-specific values where appropriate.
5. **Runtime sysupgrade:** make future upgrades understand the split `ubi_kernel` + `rootfs` layout instead of assuming a single UBI partition named `rootfs`.

A successful first boot after a DTB change would not close items 3-5; those must still be validated before considering the adaptation complete.

## Proposed direction

Keep the transition firmware and `setup` unchanged.

Adapt the VIKINGYFY AP8220 build so the resulting kernel/runtime agrees with the NAND layout already established/expected by the transition environment.

The first candidate change is to override the AP8220 NAND partition description to match the transition firmware:

```dts
partitions {
    compatible = "fixed-partitions";

    partition@0 {
        label = "rootfs";
        reg = <0x00000000 0x3e800000>;
    };

    partition@3e800000 {
        label = "ubi_kernel";
        reg = <0x3e800000 0x01800000>;
    };
};
```

The exact DTS syntax/cell width must be taken from the current upstream source rather than copied blindly from this pseudocode.

## Preferred CI implementation

Do not maintain a full fork of VIKINGYFY/immortalwrt solely for this experiment.

Add a repository-owned patch, for example:

```
patches/ap8220-1g-nand-setup-compat.patch
```

and apply it in `WRT-CORE.yml` after cloning upstream, similar to the existing Q6000 eMMC adaptation.

Prefer a dedicated AP8220 build config/workflow or an explicit opt-in condition so the patch does not silently change every IPQ807x device in the existing multi-device QCA build.

## Codex review tasks

1. Locate the exact current AP8220 DTS/DTSI in `VIKINGYFY/immortalwrt:main` and identify where `qcom,smem-part` is inherited or declared.
2. Locate the AP8220 device/image definition (likely under the qualcommax image recipes) and document how `kernel`, `root`, and sysupgrade metadata are generated.
3. Verify whether replacing/overriding the NAND partition node with the transition firmware's fixed map is sufficient for early boot and rootfs discovery.
4. Determine how the sysupgrade `root` payload is supposed to reach/use the 1000 MiB `rootfs` MTD partition. The observed `setup` fragment explicitly updates only the kernel volume; this is currently an unresolved part of the installation path.
5. Check `fstab`, `mount_root`, UBI/ubiblock behavior, platform upgrade scripts, and any `PART_NAME`/rootfs assumptions for AP8220.
6. Verify ART/caldata and MAC-address lookup behavior under the fixed partition map. Do not regress Wi-Fi calibration or board identity.
7. Check bootloader expectations for the `ubi_kernel` UBI volume and FIT payload (volume name/id, load/entry addresses, DTB selection and compression).
8. Implement the smallest isolated patch possible and add CI-time assertions that inspect the generated AP8220 image.

## Suggested CI assertions

Before publishing an AP8220 test artifact, fail the job unless all of the following are true:

- sysupgrade tar contains `sysupgrade-aliyun_ap8220/kernel` and `root`;
- kernel payload is <= 16 MiB;
- embedded DTB reports `rootfs` at `0x0 / 0x3e800000`;
- embedded DTB reports `ubi_kernel` at `0x3e800000 / 0x01800000`;
- the AP8220 kernel DTB no longer relies on `qcom,smem-part` for this 1 GiB NAND variant.

If practical, keep these checks in a small script committed to this CI repository so future upstream changes cannot silently restore an incompatible layout.

## Validation sequence

1. Build only; do not flash.
2. Extract the generated AP8220 sysupgrade archive.
3. Inspect the kernel FIT and embedded DTB.
4. Compare the generated DTB against the known-good transition firmware DTB.
5. Confirm kernel size and sysupgrade member paths.
6. Review the rootfs/upgrade path identified above.
7. Only after all static checks pass, perform a controlled device test with serial recovery available.

## Non-goals

This proposal does not attempt to change:

- the immutable transition `setup` script;
- PPE/NSS acceleration selection;
- Ethernet topology;
- Wi-Fi enable/disable policy;
- unrelated IPQ807x devices.

The first experiment should minimize variables and address only AP8220 1 GiB NAND/setup compatibility.

## Review outcome expected

Codex should either:

- turn this proposal into a minimal AP8220-specific patch plus CI validation; or
- explain, with upstream source references, why the fixed-partition hypothesis is incomplete and amend the design before any flash test.
