"""Correct the SDIO model name reported for the Fine3399 Broadcom radio."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def fix_json(path: Path) -> None:
    devices = json.loads(path.read_text(encoding="utf-8"))

    matches = [
        entry
        for entry in devices["pci"]
        if str(entry[0]).lower() == "0x02d0" and str(entry[1]).lower() == "0xa9a6"
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one 02d0:a9a6 entry, found {len(matches)}")

    entry = matches[0]
    if entry[6:] == ["Broadcom", "BCM43430"]:
        print("Fine3399 Wi-Fi model is already corrected")
        return
    if entry[6:] != ["Cypress", "CYW43455"]:
        raise SystemExit(f"unexpected model for 02d0:a9a6: {entry[6:]}")

    entry[6] = "Broadcom"
    entry[7] = "BCM43430"
    path.write_text(
        json.dumps(devices, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Corrected Fine3399 Wi-Fi model to Broadcom BCM43430")


def fix_text(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if line.split()[:2] == ["0x02d0", "0xa9a6"]
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one 02d0 0xa9a6 device, found {len(matches)}")

    index = matches[0]
    line = lines[index]
    if '"Broadcom" "BCM43430"' in line:
        print("Fine3399 libiwinfo model is already corrected")
        return
    updated, count = re.subn(
        r'"Cypress"\s+"CYW43455"', '"Broadcom" "BCM43430"', line
    )
    if count != 1:
        raise SystemExit(f"unexpected libiwinfo model: {line}")
    lines[index] = updated
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Corrected Fine3399 libiwinfo model to Broadcom BCM43430")


def main() -> int:
    path = Path(sys.argv[1])
    if path.name == "wifi_devices.json":
        fix_json(path)
    elif path.name == "devices.txt":
        fix_text(path)
    else:
        raise SystemExit(f"unsupported Wi-Fi database: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
