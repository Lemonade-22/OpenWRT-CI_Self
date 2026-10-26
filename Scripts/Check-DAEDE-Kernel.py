#!/usr/bin/env python3
"""Check the actual ophub kernel archive before packing a dae/daed and fake-flow image."""
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive')
parser.add_argument('--fakeflow', action='store_true')
parser.add_argument('--panther-x2', action='store_true', help='Compatibility alias for the Panther X2 DTB')
parser.add_argument('--dtb', action='append', default=[], help='Required board DTB; may be repeated')
args = parser.parse_args()
if args.panther_x2:
    args.dtb.append('rk3566-panther-x2.dtb')
if args.fakeflow:
    MODULAR.update({"DUMMY": "dummy", "TUN": "tun"})
configs = []
modules = set()
dtbs = set()

def scan(archive, depth=0):
    if depth > 3:
        return
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
                scan(nested, depth + 1)

with tarfile.open(args.archive, "r:*") as archive:
    scan(archive)
configs = list({data: (name, data) for name, data in configs}.values())
missing = set(args.dtb) - dtbs
if missing:
    sys.exit("::error::Missing device trees: " + ', '.join(sorted(missing)))
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
    sys.exit("::error::ophub kernel lacks required features/modules: " + ", ".join(errors))
print("Verified ophub kernel BTF, eBPF features and required module files:", name)
