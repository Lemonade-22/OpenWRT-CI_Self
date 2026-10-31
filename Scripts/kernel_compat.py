#!/usr/bin/env python3
"""Enable native ARM32 execution on ARM64 and the vendor runtime's kernel prerequisites."""
import argparse
from pathlib import Path
import re


RUNTIME = ("SYSVIPC", "NAMESPACES", "IPC_NS", "NET_NS", "PACKET", "TMPFS", "BINFMT_ELF")
ARM64 = ("COMPAT",) + RUNTIME
# Explicitly answer newly visible COMPAT prompts before Linux syncconfig.
# Alignment fixups are absent on older kernels, so they are a requested
# setting rather than a universally required final-kernel symbol.
COMPAT_OPTIONS = ("KUSER_HELPERS", "COMPAT_ALIGNMENT_FIXUPS")
# COMPAT also exposes this prompt. Keep Linux's default (no legacy instruction
# emulation), explicitly, so syncconfig never asks for an interactive answer.
COMPAT_DISABLED = ("ARMV8_DEPRECATED",)


def set_symbols(text, symbols, prefix="CONFIG_", value="y"):
    for symbol in symbols:
        name = prefix + symbol
        text = re.sub(r"^(?:# )?" + name + r"(?:=.*| is not set)\n?", "", text, flags=re.M)
        text += (f"# {name} is not set" if value == "n" else f"{name}={value}") + "\n"
    return text


def check(text, symbols, label):
    missing = ["CONFIG_" + symbol + "=y" for symbol in symbols
               if not re.search(r"^CONFIG_" + symbol + r"=y$", text, re.M)]
    if missing:
        raise SystemExit("::error::" + label + " missing " + ", ".join(missing))


def configure(root):
    # OpenWrt strips unknown CONFIG_KERNEL_* options at defconfig. Register
    # missing selectors, then let include/kernel-defaults.mk pass them to Linux.
    path = root / "config/Config-kernel.in"
    text = path.read_text(encoding="utf-8")
    for symbol in ARM64 + COMPAT_OPTIONS + COMPAT_DISABLED:
        if not re.search(r"^\s*(?:menu)?config KERNEL_" + symbol + r"\s*$", text, re.M):
            dependency = "\tdepends on aarch64\n" if symbol in ("COMPAT",) + COMPAT_OPTIONS + COMPAT_DISABLED else ""
            default = "n" if symbol in COMPAT_DISABLED else "y"
            text += f"\nconfig KERNEL_{symbol}\n\tbool\n{dependency}\tdefault {default}\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    config = root / ".config"
    selections = set_symbols(config.read_text(encoding="utf-8"), ARM64 + COMPAT_OPTIONS, "CONFIG_KERNEL_")
    selections = set_symbols(selections, COMPAT_DISABLED, "CONFIG_KERNEL_", value="n")
    config.write_text(selections, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("configure", "verify", "verify-kernel"))
    args = parser.parse_args()
    root = Path.cwd()
    if args.phase == "configure":
        configure(root)
        return
    config = (root / ".config").read_text(encoding="utf-8")
    arm64 = bool(re.search(r"^CONFIG_aarch64=y$", config, re.M))
    required = ARM64 if arm64 else RUNTIME
    if args.phase == "verify":
        check(config.replace("CONFIG_KERNEL_", "CONFIG_"), required, "OpenWrt kernel selections")
    else:
        configs = sorted(root.glob("build_dir/target-*/linux-*/linux-*/.config"))
        if not configs:
            raise SystemExit("::error::No compiled Linux .config found for compatibility verification")
        for path in configs:
            check(path.read_text(encoding="utf-8"), required, str(path))
            print("Verified kernel runtime compatibility:", path)
    if not arm64:
        print("Non-ARM64 target: ARM32 COMPAT is not required; runtime prerequisites verified.")


if __name__ == "__main__":
    main()
