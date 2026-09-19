#!/usr/bin/env python3
"""Apply dae requirements to the pinned fork's existing RK3566-capable config."""
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[2]
lock = json.loads((Path(__file__).with_name("sources.json")).read_text())["kernel"]
fork = root / "kernel-fork"
actual = subprocess.check_output(["git", "-C", str(fork), "rev-parse", "HEAD"], text=True).strip()
assert actual == lock["config_commit"], "Kernel config checkout does not match lock"
series = ".".join(lock["version"].split(".")[:2])
config = fork / lock["config_path"] / ("config-" + series)
text = config.read_text()
required = {
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
    "VETH": "m", "NETKIT": "y", "XDP_SOCKETS_DIAG": "m",
}
for key, value in required.items():
    symbol = "CONFIG_" + key
    text = re.sub(r"^(?:# )?" + symbol + r"(?:=.*| is not set)\n?", "", text, flags=re.M)
    text += (f"# {symbol} is not set" if value == "n" else f"{symbol}={value}") + "\n"
config.write_text(text)
print("Prepared kernel config:", config)
