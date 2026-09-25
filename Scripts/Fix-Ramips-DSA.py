#!/usr/bin/env python3
"""Refresh the ramips Ralink DSA patch after generic DSA tag additions."""

from pathlib import Path


GENERIC_PATCHES = (
    (
        "target/linux/generic/hack-6.18/752-net-dsa-add-rtl837x-8021ad-tag-driver.patch",
        (
            "#define DSA_TAG_PROTO_RTL837X_8021AD_VALUE\t34",
            "\tDSA_TAG_PROTO_RTL837X_8021AD\t= DSA_TAG_PROTO_RTL837X_8021AD_VALUE,",
        ),
    ),
    (
        "target/linux/generic/hack-6.18/753-net-dsa-add-rtl9303-8021ad-tag-driver.patch",
        (
            "#define DSA_TAG_PROTO_RTL9303_8021AD_VALUE\t35",
            "\tDSA_TAG_PROTO_RTL9303_8021AD\t= DSA_TAG_PROTO_RTL9303_8021AD_VALUE,",
        ),
    ),
)


def replace_hunk_header(
    text, original_old_start, original_new_start, additions, shift_starts=False
):
    headers = [
        (
            f"@@ -{original_old_start + (count if shift_starts else 0)},{6 + count} "
            f"+{original_new_start + (count if shift_starts else 0)},{7 + count} @@"
        )
        for count in range(additions + 1)
    ]
    matches = [header for header in headers if header in text]
    if len(matches) != 1:
        raise RuntimeError("Ralink DSA patch changed upstream; review its header hunks")
    return text.replace(matches[0], headers[-1], 1)


def replace_context(text, anchor, end_marker, lines):
    start = text.find(anchor)
    if start == -1 or text.find(anchor, start + 1) != -1:
        raise RuntimeError("Cannot locate unique Ralink DSA insertion")
    start += len(anchor)
    end = text.find(end_marker, start)
    if end == -1:
        raise RuntimeError("Cannot locate the end of the Ralink DSA hunk")

    allowed = {" " + line + "\n" for line in lines}
    existing = text[start:end].splitlines(keepends=True)
    if any(line not in allowed for line in existing) or len(existing) != len(set(existing)):
        raise RuntimeError("Ralink DSA patch has unexpected header context")

    context = "".join(" " + line + "\n" for line in lines)
    return text[:start] + context + text[end:]


def refresh(root):
    root = Path(root)
    patch = root / "target/linux/ramips/patches-6.18/761-net-dsa-add-ralink-metadata-tagger.patch"
    if not patch.is_file():
        print("Ralink DSA compatibility fix: target patch absent, skipping")
        return

    context = [[], []]
    applied = []
    for relative_path, lines in GENERIC_PATCHES:
        generic = root / relative_path
        if not generic.is_file():
            continue
        generic_text = generic.read_text()
        for line in lines:
            if "+" + line + "\n" not in generic_text:
                raise RuntimeError(f"Generic DSA patch changed upstream: {relative_path}")
        for index, line in enumerate(lines):
            context[index].append(line)
        applied.append(generic.name)

    if not applied:
        print("Ralink DSA compatibility fix: generic patches absent, skipping")
        return

    original = patch.read_text()
    text = replace_hunk_header(original, 57, 57, len(applied))
    text = replace_hunk_header(text, 91, 92, len(applied), shift_starts=True)
    text = replace_context(
        text,
        "+#define DSA_TAG_PROTO_RALINK_VALUE\t\t32\n",
        " \n",
        context[0],
    )
    text = replace_context(
        text,
        "+\tDSA_TAG_PROTO_RALINK\t\t= DSA_TAG_PROTO_RALINK_VALUE,\n",
        " };\n",
        context[1],
    )

    if text != original:
        patch.write_text(text)
        print("Refreshed Ralink DSA patch for " + ", ".join(applied))
    else:
        print("Ralink DSA patch already refreshed")


if __name__ == "__main__":
    refresh(Path.cwd())

