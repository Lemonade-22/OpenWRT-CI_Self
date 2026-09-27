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
