#!/usr/bin/env python3
"""Check the actual ophub kernel archive before packing a dae/daed, fake-flow and SONiC fullcone image."""
import argparse
import io
import re
import sys
import tarfile

BUILTIN = ("BPF", "BPF_SYSCALL", "BPF_JIT", "CGROUPS", "CGROUP_BPF",
           "KPROBES", "KPROBE_EVENTS", "BPF_EVENTS", "DEBUG_INFO_BTF",
           "BPF_STREAM_PARSER", "XDP_SOCKETS", "NET_CLS_ACT",
           "NET_INGRESS", "NET_EGRESS", "NET_NS")
MODULAR = {"NET_SCH_INGRESS": "sch_ingress", "NET_CLS_BPF": "cls_bpf",
           "NET_ACT_BPF": "act_bpf", "VETH": "veth"}

# SONiC fullcone kernel requirements. Builtins must be exactly y; NAT frontends
# may be built in or modular, but must ship their module file when modular.
SONIC = {
    "NF_NAT_FULLCONE": ("y",),
    "NF_CT_PROTO_UDPLITE": ("y",),
    "NF_CT_PROTO_SCTP": ("y",),
    "NF_NAT": ("y", "m"),
    "NF_NAT_MASQUERADE": ("y", "m"),
    "NF_TABLES": ("y", "m"),
    "NFT_NAT": ("y", "m"),
    "NFT_MASQ": ("y", "m"),
    "NETFILTER_XT_TARGET_MASQUERADE": ("y", "m"),
}
SONIC_MODULES = {
    "NF_NAT": "nf_nat",
    "NF_TABLES": "nf_tables",
    "NFT_NAT": ("nft_nat", "nft_chain_nat"),
    "NFT_MASQ": "nft_masq",
    "NETFILTER_XT_TARGET_MASQUERADE": "xt_MASQUERADE",
}

# Fine3399 has an onboard RK3399 stmmac GMAC and an RTL8152 USB NIC. Panther X2
# needs no extra symbol checks beyond the shared dae/fakeflow ones.
DEVICES = {
    "fine3399": {
        "symbols": {
            "STMMAC_ETH": ("y", "m"),
            "DWMAC_ROCKCHIP": ("y", "m"),
            "REALTEK_PHY": ("y", "m"),
            "USB_RTL8152": ("y", "m"),
        },
        "modules": {
            "STMMAC_ETH": "stmmac",
            "DWMAC_ROCKCHIP": "dwmac_rockchip",
            "REALTEK_PHY": "realtek",
            "USB_RTL8152": "r8152",
        },
        "label": "Fine3399 network drivers (STMMAC, DWMAC_ROCKCHIP, REALTEK_PHY, USB_RTL8152)",
    },
    "panther-x2": {
        "symbols": {},
        "modules": {},
        "label": "Panther X2 has no extra kernel symbol checks",
    },
}


def collect(archive, depth=0, configs=None, modules=None, dtbs=None):
    """Collect kernel configs, module basenames and DTB basenames from a (nested) archive."""
    if configs is None:
        configs, modules, dtbs = [], set(), set()
    if depth > 3:
        return configs, modules, dtbs
    for item in archive:
        if not item.isfile():
            continue
        name = item.name.rsplit("/", 1)[-1]
        if name.endswith('.dtb') and item.size > 0:
            dtbs.add(name)
        match = re.match(r"(.+)\.ko(?:\.(?:gz|xz|zst))?$", name)
        if match:
            modules.add(match.group(1))
        if name == ".config" or name == "config" or name.startswith("config-"):
            data = archive.extractfile(item).read().decode("utf-8", errors="replace")
            if "CONFIG_BPF=" in data:
                configs.append((item.name, data))
        elif name.endswith((".tar.gz", ".tar.xz", ".tgz", ".tar")):
            with tarfile.open(fileobj=io.BytesIO(archive.extractfile(item).read()), mode="r:*") as nested:
                collect(nested, depth + 1, configs, modules, dtbs)
    return configs, modules, dtbs


def check_requirement(values, required, modules, module_files, label, errors):
    """Append errors for missing/incorrect symbols and for missing modules of modular symbols."""
    for key, allowed in required.items():
        actual = values.get(key)
        if actual not in allowed:
            errors.append(f"{key}=" + "/".join(allowed) + f" ({label})")
            continue
        module = module_files.get(key)
        required_modules = (module,) if isinstance(module, str) else (module or ())
        for filename in required_modules:
            if actual == "m" and filename not in modules:
                errors.append(f"module file {filename}.ko ({label})")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--fakeflow', action='store_true')
    parser.add_argument('--sonic', action='store_true', help='Require SONiC fullcone kernel support')
    parser.add_argument('--device', action='append', choices=sorted(DEVICES), default=[],
                        help='Require the kernel features of a device; may be repeated')
    parser.add_argument('--panther-x2', action='store_true', help='Compatibility alias for the Panther X2 DTB')
    parser.add_argument('--dtb', action='append', default=[], help='Required board DTB; may be repeated')
    args = parser.parse_args(argv)
    if args.panther_x2:
        args.dtb.append('rk3566-panther-x2.dtb')
    modular = dict(MODULAR)
    if args.fakeflow:
        modular.update({"DUMMY": "dummy", "TUN": "tun"})
    with tarfile.open(args.archive, "r:*") as archive:
        configs, modules, dtbs = collect(archive)
    configs = list({data: (name, data) for name, data in configs}.values())
    missing = set(args.dtb) - dtbs
    if missing:
        sys.exit("::error::Missing device trees: " + ', '.join(sorted(missing)))
    if len(configs) != 1:
        sys.exit("::error::Cannot uniquely verify ophub kernel config; expected one kernel config in archive")
    name, config = configs[0]
    values = dict(re.findall(r"^CONFIG_(\w+)=(\S+)$", config, re.M))
    errors = [key + "=y" for key in BUILTIN if values.get(key) != "y"]
    for key, module in modular.items():
        if values.get(key) not in ("y", "m"):
            errors.append(key + "=y/m")
        elif values[key] == "m" and module not in modules:
            errors.append("module file " + module + ".ko")
    if args.sonic:
        check_requirement(values, SONIC, modules, SONIC_MODULES, "SONiC fullcone", errors)
        for key, value in sorted(values.items()):
            if "FULLCONE" in key.upper() and key != "NF_NAT_FULLCONE":
                errors.append(f"legacy fullcone config CONFIG_{key}={value}")
        for module in sorted(modules):
            if "fullcone" in module.lower():
                errors.append(f"legacy fullcone module {module}.ko")
    devices = list(dict.fromkeys(args.device))
    for device in devices:
        specification = DEVICES[device]
        check_requirement(values, specification["symbols"], modules,
                          specification["modules"], device, errors)
    if errors:
        sys.exit("::error::ophub kernel lacks required features/modules: " + ", ".join(errors))
    print("Verified ophub kernel BTF, eBPF features and required module files:", name)
    if args.sonic:
        print("Verified SONiC fullcone kernel support: NF_NAT_FULLCONE, NF_CT_PROTO_UDPLITE/SCTP, "
              "NF_NAT, NF_TABLES, NFT_NAT, NFT_MASQ and xt_MASQUERADE")
    for device in devices:
        print("Verified " + DEVICES[device]["label"])


if __name__ == "__main__":
    main()
