#!/usr/bin/env python3
"""Refresh the ramips Ralink DSA patch after the generic RTL837x addition."""
from pathlib import Path

def refresh(root):
    root = Path(root)
    patch = root / "target/linux/ramips/patches-6.18/761-net-dsa-add-ralink-metadata-tagger.patch"
    generic = root / "target/linux/generic/hack-6.18/752-net-dsa-add-rtl837x-8021ad-tag-driver.patch"
    if not patch.is_file() or not generic.is_file():
        print("Ralink DSA compatibility fix: patch pair absent, skipping")
        return
    text = patch.read_text()
    generic_text = generic.read_text()
    replacements = [
        ("@@ -57,6 +57,7 @@ struct tc_action;", "@@ -57,7 +57,8 @@ struct tc_action;"),
        ("@@ -91,6 +92,7 @@ enum dsa_tag_protocol {", "@@ -92,7 +93,8 @@ enum dsa_tag_protocol {"),
    ]
    for old, new in replacements:
        if old not in text and new not in text:
            raise RuntimeError("Ralink DSA patch changed upstream; review its header hunks")
    lines = [
        "#define DSA_TAG_PROTO_RTL837X_8021AD_VALUE\t34",
        "\tDSA_TAG_PROTO_RTL837X_8021AD\t= DSA_TAG_PROTO_RTL837X_8021AD_VALUE,",
    ]
    anchors = [
        "+#define DSA_TAG_PROTO_RALINK_VALUE\t\t32\n",
        "+\tDSA_TAG_PROTO_RALINK\t\t= DSA_TAG_PROTO_RALINK_VALUE,\n",
    ]
    for line, anchor in zip(lines, anchors):
        if "+" + line not in generic_text:
            raise RuntimeError("RTL837x DSA patch changed upstream; review before applying")
        if " " + line + "\n" not in text:
            if text.count(anchor) != 1:
                raise RuntimeError("Cannot locate unique Ralink DSA insertion")
            text = text.replace(anchor, anchor + " " + line + "\n", 1)
    for old, new in replacements:
        text = text.replace(old, new, 1)
    if text != patch.read_text():
        patch.write_text(text)
        print("Refreshed Ralink DSA patch for RTL837x header additions")
    else:
        print("Ralink DSA patch already refreshed")

if __name__ == "__main__":
    refresh(Path.cwd())
