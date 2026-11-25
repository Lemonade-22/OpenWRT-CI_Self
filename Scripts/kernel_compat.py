#!/usr/bin/env python3
"""Register honk's TCX kernel symbols so make defconfig keeps them.

OpenWrt drops unknown CONFIG_KERNEL_* options at defconfig: kconfig silently
discards a symbol whose dependencies cannot be satisfied. The symbols honk
needs therefore have to be declared in config/Config-kernel.in first, then
selected in .config, and only then does include/kernel-defaults.mk hand them to
Linux. The same three phases are what the workflow calls.

The ARM32 compatibility layer that used to live here (COMPAT plus the SysV IPC
and namespace set) was removed: it existed only so zte-mesh could exec the
vendor's 32-bit ARM daemon, and no build in this repository selects that
package.
"""
import argparse
from pathlib import Path
import re


# honk (Rust + eBPF transparent proxy) attaches through TCX. NET_XGRESS is a
# hidden option selected by NET_CLS_ACT, which generic config leaves off, so
# both have to be opened. ramips still ships an older kernel and is skipped.
TCX = ("NET_CLS_ACT", "NET_XGRESS")


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


def kernel_option(symbol, kind, default):
    text = f"\nconfig KERNEL_{symbol}\n\t{kind}\n"
    return text + f"\tdefault {default}\n"


def tcx_wanted(root):
    """honk needs TCX; ramips (mt7621 included) still ships an older kernel."""
    config = root / ".config"
    if not config.exists():
        return False
    text = config.read_text(encoding="utf-8", errors="replace")
    return not re.search(r"^CONFIG_TARGET_ramips(?:=|_)", text, re.M)


def configure_tcx(root):
    path = root / "config/Config-kernel.in"
    text = path.read_text(encoding="utf-8")
    for symbol in TCX:
        if not re.search(r"^\s*(?:menu)?config KERNEL_" + symbol + r"\s*$", text, re.M):
            text += kernel_option(symbol, "bool", "y")
    path.write_text(text, encoding="utf-8", newline="\n")
    config = root / ".config"
    selections = set_symbols(config.read_text(encoding="utf-8"), TCX, "CONFIG_KERNEL_")
    config.write_text(selections, encoding="utf-8", newline="\n")


def verify_tcx(root, phase):
    if phase == "verify":
        selections = (root / ".config").read_text(encoding="utf-8").replace("CONFIG_KERNEL_", "CONFIG_")
        check(selections, TCX, "honk TCX kernel selections")
        return
    configs = sorted(root.glob("build_dir/target-*/linux-*/linux-*/.config"))
    if not configs:
        raise SystemExit("::error::No compiled Linux .config found for honk TCX verification")
    for path in configs:
        check(path.read_text(encoding="utf-8"), TCX, str(path))
        print("Verified honk TCX:", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("configure", "verify", "verify-kernel"))
    args = parser.parse_args()
    root = Path.cwd()
    if not tcx_wanted(root):
        print("honk TCX layer skipped: ramips target keeps its own kernel")
        return
    if args.phase == "configure":
        configure_tcx(root)
        return
    verify_tcx(root, args.phase)


if __name__ == "__main__":
    main()
