#!/usr/bin/env python3
"""Check the actual ophub kernel archive before packing a dae/daed image."""
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
configs = []
modules = set()
panther_dtb = False

def scan(archive, depth=0):
    global panther_dtb
    if depth > 3:
        return
    for item in archive:
        if not item.isfile():
            continue
        name = item.name.rsplit("/", 1)[-1]
        if name == "rk3566-panther-x2.dtb":
            panther_dtb = True
        match = re.match(r"(.+)\.ko(?:\.(?:gz|xz|zst))?$", name)
        if match:
            modules.add(match.group(1))
        if name == ".config" or name == "config" or name.startswith("config-"):
            data = archive.extractfile(item).read().decode("utf-8", errors="replace")
            if "CONFIG_BPF=" in data:
                configs.append((item.name, data))
        elif name.endswith((".tar.gz", ".tar.xz", ".tgz", ".tar")):
            with tarfile.open(fileobj=io.BytesIO(archive.extractfile(item).read()), mode="r:*") as nested:
                scan(nested, depth + 1)

with tarfile.open(sys.argv[1], "r:*") as archive:
    scan(archive)
configs = list({data: (name, data) for name, data in configs}.values())
if "--panther-x2" in sys.argv and not panther_dtb:
    sys.exit("::error::Missing Panther X2 device tree")
if len(configs) != 1:
    sys.exit("::error::Cannot uniquely verify ophub kernel config; expected one kernel config in archive")
name, config = configs[0]
values = dict(re.findall(r"^CONFIG_(\w+)=(\S+)$", config, re.M))
errors = [key + "=y" for key in BUILTIN if values.get(key) != "y"]
for key, module in MODULAR.items():
    if values.get(key) not in ("y", "m"):
        errors.append(key + "=y/m")
    elif values[key] == "m" and module not in modules:
        errors.append("module file " + module + ".ko")
if errors:
    sys.exit("::error::ophub kernel lacks dae/daed requirements: " + ", ".join(errors))
print("Verified ophub kernel BTF, eBPF features and required module files:", name)
