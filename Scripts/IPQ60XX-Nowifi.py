#!/usr/bin/env python3
"""Prepare and check the two-device VIKINGYFY no-WiFi build."""
from pathlib import Path
import re
import sys
import tarfile

DEVICES = ("link_nn6000-v2", "zn_m2")
WIFI_PACKAGES = (
    "kmod-ath", "kmod-ath11k", "kmod-ath11k-ahb", "kmod-ath11k-pci",
    "ath11k-firmware-ipq6018", "ath11k-firmware-ipq6018-ddwrt",
    "ath11k-firmware-qcn9074", "ath11k-firmware-qcn9074-ddwrt", "wpad-openssl",
)
BOARD_PACKAGES = {"link_nn6000-v2": "ipq-wifi-link_nn6000", "zn_m2": "ipq-wifi-zn_m2"}
REQUIRED_PACKAGES = (
    "luci-theme-footstrap", "ca-bundle", "kmod-sched-core", "kmod-sched-bpf",
    "kmod-veth", "kmod-xdp-sockets-diag", "kmod-nft-tproxy",
)
BUILTIN = (
    "BPF", "BPF_SYSCALL", "BPF_JIT", "DEBUG_INFO_BTF", "CGROUPS", "CGROUP_BPF",
    "KPROBES", "KPROBE_EVENTS", "BPF_EVENTS", "BPF_STREAM_PARSER", "XDP_SOCKETS",
    "NET_NS", "NET_CLS_ACT", "NET_INGRESS", "NET_EGRESS",
)
MODULES = {
    "NET_SCH_INGRESS": "sch_ingress", "NET_CLS_BPF": "cls_bpf",
    "NET_ACT_BPF": "act_bpf", "VETH": "veth",
    "XDP_SOCKETS_DIAG": "xsk_diag", "NFT_TPROXY": "nft_tproxy",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_config(path):
    return dict(re.findall(r"^CONFIG_([^=\n]+)=(.*)$", path.read_text(), re.M))


def forbidden_package(name):
    return (
        name.startswith(("kmod-ath", "ath11k-firmware-", "ipq-wifi-", "wpad", "hostapd"))
        or any(part in name for part in ("aurora", "gecoosac", "homeproxy", "wolultra"))
    )


def prepare():
    target = Path("target/linux/qualcommax")
    require((target / "files/arch/arm64/boot/dts/qcom/ipq6018-nowifi.dtsi").is_file(),
            "The selected source lacks VIKINGYFY's ipq6018-nowifi.dtsi")
    # Per-device rootfs defaults can force drivers back to m despite .config=n.
    # Drop only the wireless defaults, retaining all Ethernet and storage packages.
    pattern = r"(?<![\w-])(?:" + "|".join(map(re.escape, WIFI_PACKAGES)) + r")(?![\w-])"
    for path in (target / "Makefile", target / "ipq60xx/target.mk"):
        original = path.read_text()
        path.write_text(re.sub(pattern, "", original))
    path = target / "image/ipq60xx.mk"
    text = path.read_text()
    for device, package in BOARD_PACKAGES.items():
        pattern = rf"(?ms)^define Device/{re.escape(device)}\n.*?^endef$"
        matches = list(re.finditer(pattern, text))
        require(len(matches) == 1, f"Expected one image definition for {device}")
        block = matches[0].group()
        removal = f"\tDEVICE_PACKAGES += -{package}\n"
        if removal not in block:
            text = text[:matches[0].start()] + block[:-len("endef")] + removal + "endef" + text[matches[0].end():]
    path.write_text(text)
    # Feeds installation may already have cached target defaults.
    for name in (".targetinfo", ".config-target.in", ".config-package.in"):
        (Path("tmp") / name).unlink(missing_ok=True)
    print("Removed wireless defaults for the two-device no-WiFi build")


def verify_config():
    config = read_config(Path(".config"))
    selected = {key.removeprefix("TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_")
                for key, value in config.items()
                if key.startswith("TARGET_DEVICE_qualcommax_ipq60xx_DEVICE_") and value == "y"}
    require(selected == set(DEVICES), f"Unexpected device selection: {selected}")
    for package in REQUIRED_PACKAGES:
        require(config.get("PACKAGE_" + package) == "y", f"Missing package: {package}")
    for key, value in config.items():
        if key.startswith("PACKAGE_") and value in ("y", "m"):
            require(not forbidden_package(key[8:]), f"Unwanted package: {key}")
    dts = Path("target/linux/qualcommax/dts")
    for name in ("ipq6000-link.dtsi", "ipq6000-cmiot.dtsi"):
        require("ipq6018-nowifi.dtsi" in (dts / name).read_text(),
                f"Upstream no-WiFi device tree substitution did not apply: {name}")
    print("Verified two devices, no-WiFi configuration and Footstrap")


def verify_build():
    configs = list(Path("build_dir").glob("target-*/linux-qualcommax_ipq60xx/linux-*/.config"))
    require(len(configs) == 1, "Cannot uniquely locate the compiled IPQ60xx kernel configuration")
    config = read_config(configs[0])
    for key in BUILTIN:
        require(config.get(key) == "y", f"Compiled kernel lacks CONFIG_{key}=y")
    for key, module in MODULES.items():
        require(config.get(key) in ("y", "m"), f"Compiled kernel lacks CONFIG_{key}")
        if config[key] == "m":
            require(any(configs[0].parent.rglob(module + ".ko")), f"Missing module: {module}.ko")
    output = Path("bin/targets/qualcommax/ipq60xx")
    for device in DEVICES:
        images = list(output.glob(f"*{device}*sysupgrade.bin"))
        manifests = list(output.glob(f"*{device}*.manifest"))
        require(bool(images) and bool(manifests), f"Missing firmware or manifest for {device}")
        for manifest in manifests:
            packages = {line.split()[0] for line in manifest.read_text().splitlines() if line.strip()}
            require(not any(forbidden_package(name) for name in packages),
                    f"Unwanted wireless/application/theme package in {manifest.name}")
            require(set(REQUIRED_PACKAGES) <= packages, f"Missing runtime packages in {manifest.name}")
        if device == "link_nn6000-v2":
            for image in images:
                with tarfile.open(image) as archive:
                    kernels = [m for m in archive if m.isfile() and m.name.endswith("/kernel")]
                    require(len(kernels) == 1, f"Cannot identify FIT kernel in {image.name}")
                    require(kernels[0].size <= 6144 * 1024, "NN6000 v2 kernel exceeds its 6 MiB partition")
    print("Verified actual eBPF/BTF kernel, firmware manifests and NN6000 v2 kernel size")


if __name__ == "__main__":
    commands = {"prepare": prepare, "verify-config": verify_config, "verify-build": verify_build}
    try:
        require(len(sys.argv) == 2 and sys.argv[1] in commands,
                "Usage: IPQ60XX-Nowifi.py prepare|verify-config|verify-build")
        commands[sys.argv[1]]()
    except (ValueError, OSError, tarfile.TarError) as error:
        sys.exit(f"::error::{error}")
