#!/usr/bin/env python3
"""Apply dae, fake-flow, SONiC and Fine3399 requirements to the pinned fork's existing Rockchip ARM64 config."""
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Scripts"))
from kernel_compat import ARM64

FAKEFLOW = {
    "BPF": "y", "BPF_SYSCALL": "y", "BPF_JIT": "y",
    "CGROUPS": "y", "CGROUP_BPF": "y", "KPROBES": "y",
    "KPROBE_EVENTS": "y", "BPF_EVENTS": "y",
    "DEBUG_INFO": "y", "DEBUG_INFO_NONE": "n",
    "DEBUG_INFO_REDUCED": "n", "DEBUG_INFO_SPLIT": "n",
    "DEBUG_INFO_DWARF5": "y", "DEBUG_INFO_BTF": "y",
    "BPF_STREAM_PARSER": "y", "XDP_SOCKETS": "y",
    "NET": "y", "NET_SCHED": "y", "NET_CLS": "y", "NET_CLS_ACT": "y",
    "NET_INGRESS": "y", "NET_EGRESS": "y", "NAMESPACES": "y", "NET_NS": "y",
    "NET_SCH_INGRESS": "m", "NET_CLS_BPF": "m", "NET_ACT_BPF": "m",
    "DUMMY": "m", "TUN": "m",
    "VETH": "m", "NETKIT": "y", "XDP_SOCKETS_DIAG": "m",
}

# SONiC fullcone NAT (nf_nat core + nft_masq + xt_MASQUERADE) selected by the
# fullconenat-sonic userspace package.
SONIC = {
    "NF_NAT_FULLCONE": "y",
    "NF_CT_PROTO_UDPLITE": "y",
    "NF_CT_PROTO_SCTP": "y",
    "NF_NAT": "m",
    "NF_NAT_MASQUERADE": "y",
    "NF_TABLES": "m",
    "NFT_NAT": "m",
    "NFT_MASQ": "m",
    "NETFILTER_XT_TARGET_MASQUERADE": "m",
    "NETFILTER_XT_NAT": "m",
}

# Fine3399 (RK3399) networking: onboard stmmac GMAC plus the RTL8152 USB NIC.
DEVICE = {
    "STMMAC_ETH": "y",
    "STMMAC_PLATFORM": "y",
    "DWMAC_ROCKCHIP": "y",
    "DWMAC_GENERIC": "y",
    "REALTEK_PHY": "y",
    "USB_RTL8152": "m",
    "BRIDGE": "y",
    "BRIDGE_VLAN_FILTERING": "y",
    "VLAN_8021Q": "m",
}

# Existing pinned config symbols the SONiC/Fine3399 additions depend on. These
# must already be present before the config is rewritten; a missing prerequisite
# means the fork config is not the expected Rockchip ARM64 one, so fail loudly.
PREREQUISITES = {
    "ARCH_ROCKCHIP": ("y",),
    "OF": ("y",),
    "USB": ("y",),
    "USB_SUPPORT": ("y",),
    "PHYLIB": ("y",),
    "MII": ("y",),
    "NETFILTER_ADVANCED": ("y",),
    "NF_CONNTRACK": ("y", "m"),
}


def config_values(text):
    """Parse a kernel .config into a symbol -> value mapping (symbols without CONFIG_)."""
    return dict(re.findall(r"^CONFIG_(\w+)=(\S+)$", text, re.M))


def missing_prerequisites(values):
    """Return a list of unmet prerequisite descriptions in PREREQUISITES order."""
    missing = []
    for symbol, allowed in PREREQUISITES.items():
        actual = values.get(symbol)
        if actual not in allowed:
            missing.append("CONFIG_" + symbol + "=" + "/".join(allowed))
    return missing


def set_symbols(text, symbols):
    """Rewrite every symbol in symbols with the required value, preserving LF formatting."""
    for symbol, value in symbols.items():
        name = "CONFIG_" + symbol
        text = re.sub(r"^(?:# )?" + name + r"(?:=.*| is not set)\n?", "", text, flags=re.M)
        text += (f"# {name} is not set" if value == "n" else f"{name}={value}") + "\n"
    return text


def remove_legacy_fullcone(text):
    """Drop legacy fullcone symbols (nft/iptables variants) superseded by NF_NAT_FULLCONE.

    The pinned ophub config still carries CONFIG_NFT_FULLCONE and
    CONFIG_NETFILTER_XT_TARGET_FULLCONENAT from the removed out-of-tree fullcone
    packages; the SONiC patches replace them, so keep only NF_NAT_FULLCONE.
    """
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r"^(?:# )?CONFIG_(\w+)(?:=.*| is not set)\s*$", line)
        if match and "FULLCONE" in match.group(1).upper() and match.group(1) != "NF_NAT_FULLCONE":
            continue
        lines.append(line)
    return "".join(lines)


def prepare(root, lock):
    """Prepare the kernel config inside root/kernel-fork for the locked kernel lock entry."""
    fork = Path(root) / "kernel-fork"
    actual = subprocess.check_output(
        ["git", "-C", str(fork), "rev-parse", "HEAD"], text=True
    ).strip()
    assert actual == lock["config_commit"], "Kernel config checkout does not match lock"
    series = ".".join(lock["version"].split(".")[:2])
    config = fork / lock["config_path"] / ("config-" + series)
    text = config.read_text(encoding="utf-8")
    values = config_values(text)
    missing = missing_prerequisites(values)
    if missing:
        raise SystemExit(
            "::error::Kernel config lacks SONiC/Fine3399 prerequisites: " + ", ".join(missing)
        )
    required = dict(FAKEFLOW)
    required.update(SONIC)
    required.update(DEVICE)
    required.update(dict.fromkeys(ARM64, "y"))
    text = remove_legacy_fullcone(text)
    config.write_text(set_symbols(text, required), encoding="utf-8", newline="\n")
    print("Prepared kernel config:", config)
    return config


def main():
    root = Path(__file__).resolve().parents[2]
    lock = json.loads(
        Path(__file__).with_name("sources.json").read_text(encoding="utf-8")
    )["kernel"]
    prepare(root, lock)


if __name__ == "__main__":
    main()
