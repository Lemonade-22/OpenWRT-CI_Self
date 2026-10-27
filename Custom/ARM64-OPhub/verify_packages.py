#!/usr/bin/env python3
"""Verify that upstream-selected LuCI packages survived `make defconfig`.

Upstream `Scripts/Settings.sh` (VIKINGYFY/immortalwrt) appends package
selections for the chosen LuCI theme to `.config` before buildroot runs
`make defconfig`:

    CONFIG_PACKAGE_luci-theme-$WRT_THEME=y
    CONFIG_PACKAGE_luci-app-$WRT_THEME=y
    CONFIG_PACKAGE_luci-app-$WRT_THEME-config=y

`make defconfig` silently drops selections for packages that do not exist in
the selected feeds.  For the default theme `vantage` only two of the three
theme packages exist (`luci-app-vantage` and `luci-theme-vantage` from
https://github.com/anothaDev/luci-theme-vantage); `luci-app-vantage-config`
does not, so buildroot legitimately drops that one selection.

The exception must stay narrow: a theme companion is tolerated as absent only
when its `PACKAGE_` symbol is genuinely missing from `tmp/.config-package.in`.
A companion that IS defined but got dropped is a real error (the theme would
be installed without its dashboard/configuration), and every non-theme package
that got dropped is always an error.

Usage (from the OpenWrt build root, after `make defconfig`):

    python3 Custom/ARM64-OPhub/verify_packages.py \\
        --requested output/upstream-luci-selected.config \\
        --actual .config \\
        --definitions tmp/.config-package.in \\
        --theme vantage
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# e.g. CONFIG_PACKAGE_luci-app-vantage=y
_PACKAGE_LINE = re.compile(r"^CONFIG_PACKAGE_(?P<package>[^=\s]+)=(?P<value>\S*)$")
# e.g. "config PACKAGE_luci-app-vantage" in tmp/.config-package.in
_DEFINITION_LINE = re.compile(r"^\s*config\s+PACKAGE_(?P<package>\S+)\s*$")


def _stripped_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


def _requested_lines(text: str) -> list[str]:
    """Return the meaningful selection lines of the saved upstream config."""
    return [line for line in _stripped_lines(text) if line and not line.startswith("#")]


def _package_name(line: str) -> str | None:
    match = _PACKAGE_LINE.match(line)
    return match.group("package") if match else None


def _defined_packages(definitions: str) -> set[str]:
    """Return package names that have a `config PACKAGE_<name>` definition."""
    defined = set()
    for line in definitions.splitlines():
        match = _DEFINITION_LINE.match(line)
        if match:
            defined.add(match.group("package"))
    return defined


def _theme_companions(theme: str) -> set[str]:
    """The two optional per-theme companion packages upstream selects."""
    return {"luci-app-%s" % theme, "luci-app-%s-config" % theme}


def evaluate(
    requested: str,
    actual: str,
    definitions: str,
    theme: str,
) -> tuple[list[str], list[str]]:
    """Return ``(dropped, skipped_companions)`` for the saved selections.

    ``dropped`` preserves input order.  ``skipped_companions`` lists the theme
    companion package names that were allowed to be absent because they are
    not defined by the selected feeds.
    """
    actual_lines = {line for line in _stripped_lines(actual) if line}
    defined = _defined_packages(definitions)
    companions = _theme_companions(theme)

    dropped: list[str] = []
    skipped: list[str] = []
    for line in _requested_lines(requested):
        if line in actual_lines:
            continue
        package = _package_name(line)
        if package in companions and package not in defined:
            # Optional theme companion that the selected feeds do not provide.
            # Absent by design: it is not a dropped package.
            skipped.append(package)
            continue
        dropped.append(line)
    return dropped, skipped


def missing(requested: str, actual: str, definitions: str, theme: str) -> list[str]:
    """Return requested lines dropped by buildroot (input order).

    A line is satisfied when the identical stripped line exists in ``actual``.
    The only tolerated absences are the two theme companion packages when
    their ``PACKAGE_`` symbol is not defined in ``definitions``.
    """
    return evaluate(requested, actual, definitions, theme)[0]


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that upstream-selected LuCI packages survived "
            "`make defconfig`."
        )
    )
    parser.add_argument("--requested", required=True, help="saved upstream LuCI selections")
    parser.add_argument("--actual", required=True, help="generated .config after make defconfig")
    parser.add_argument("--definitions", required=True, help="tmp/.config-package.in")
    parser.add_argument("--theme", required=True, help="upstream theme name, e.g. vantage")
    args = parser.parse_args(argv)

    try:
        requested = _read(args.requested)
        actual = _read(args.actual)
        definitions = _read(args.definitions)
    except OSError as exc:
        print("::error::Cannot read package verification input: %s" % exc)
        return 1

    dropped, skipped = evaluate(requested, actual, definitions, args.theme)

    for package in skipped:
        print(
            "Skipping absent theme companion package %s "
            "(not defined by the selected feeds)" % package
        )

    if dropped:
        for line in dropped:
            print("::error::Upstream LuCI package was dropped: %s" % line)
        return 1

    print(
        "All selected upstream LuCI packages are present in the generated "
        ".config (theme: %s)" % args.theme
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
