#!/usr/bin/env python3
"""Refresh the ramips Ralink DSA patch after generic DSA tag additions.

The generic hack-6.18 patches insert their tag into include/net/dsa.h before
the Ralink patch does, so the Ralink hunk must carry those lines as context
and count them. Nothing here is pinned to a number: tag values, tag names and
hunk sizes are read from the patches themselves, which is why upstream
renumbering no longer breaks the build.
"""

import re
import sys
from pathlib import Path

# tag name -> patch that adds it
GENERIC_PATCHES = (
    (
        "target/linux/generic/hack-6.18/752-net-dsa-add-rtl837x-8021ad-tag-driver.patch",
        "RTL837X_8021AD",
    ),
    (
        "target/linux/generic/hack-6.18/753-net-dsa-add-rtl9303-8021ad-tag-driver.patch",
        "RTL9303_8021AD",
    ),
)

DEFINE_ANCHOR = re.compile(r"^\+#define DSA_TAG_PROTO_RALINK_VALUE\s+\d+\s*$")
ENUM_ANCHOR = re.compile(r"^\+\tDSA_TAG_PROTO_RALINK\t+= DSA_TAG_PROTO_RALINK_VALUE,\s*$")
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def tag_lines(generic_text, tag):
    """The #define and enum lines the generic patch adds for one DSA tag."""
    define = re.search(
        r"^\+#define DSA_TAG_PROTO_%s_VALUE\s+(\d+)\s*$" % tag, generic_text, re.M
    )
    enum = re.search(
        r"^\+\tDSA_TAG_PROTO_%s\t+= DSA_TAG_PROTO_%s_VALUE,\s*$" % (tag, tag),
        generic_text,
        re.M,
    )
    if not define or not enum:
        raise RuntimeError("Generic DSA patch lost the %s tag; review hack-6.18" % tag)
    return (
        "#define DSA_TAG_PROTO_%s_VALUE\t%s" % (tag, define.group(1)),
        "\tDSA_TAG_PROTO_%s\t= DSA_TAG_PROTO_%s_VALUE," % (tag, tag),
    )


def stale_context(line, tags):
    """A context line that merely repeats an older copy of a generic tag."""
    if not line.startswith(" "):
        return False
    name = re.match(r"^ #define DSA_TAG_PROTO_(\w+)_VALUE\s+\d+\s*$", line)
    if name and name.group(1) in tags:
        return True
    name = re.match(r"^ \tDSA_TAG_PROTO_(\w+)\t+= DSA_TAG_PROTO_\1_VALUE,\s*$", line)
    return bool(name and name.group(1) in tags)


def rebuild(body, anchor, tags, fresh):
    """Put the current generic context lines immediately before our added line."""
    hits = [i for i, line in enumerate(body) if anchor.match(line)]
    if len(hits) != 1:
        raise RuntimeError("Ralink DSA hunk lost its %s line" % anchor.pattern)
    at = hits[0]
    start = at
    while start > 0 and stale_context(body[start - 1], tags):
        start -= 1
    body[start:at] = [" " + line + "\n" for line in fresh]
    return at - start, len(fresh)


def split(text):
    head, hunks, cur = [], [], None
    for line in text.splitlines(keepends=True):
        if line.startswith("@@"):
            cur = [[], []]
            hunks.append((line, cur))
        elif cur is None:
            head.append(line)
        else:
            cur[0].append(line)
    return head, hunks


def reheader(header, stripped, added):
    hit = HUNK_HEADER.match(header.rstrip("\n"))
    if not hit:
        raise RuntimeError("Unreadable Ralink DSA hunk header: %r" % header)
    old_start, old_count, new_start, new_count, tail = hit.groups()
    old_count = int(old_count) if old_count else 1
    new_count = int(new_count) if new_count else 1
    delta = added - stripped
    return "@@ -%d,%d +%d,%d @@%s\n" % (
        int(old_start),
        old_count + delta,
        int(new_start),
        new_count + delta,
        tail,
    )


def refresh(root):
    root = Path(root)
    patch = root / "target/linux/ramips/patches-6.18/761-net-dsa-add-ralink-metadata-tagger.patch"
    if not patch.is_file():
        print("Ralink DSA compatibility fix: target patch absent, skipping")
        return 0

    tags, defines, enums, applied = set(), [], [], []
    for relative_path, tag in GENERIC_PATCHES:
        generic = root / relative_path
        if not generic.is_file():
            continue
        define_line, enum_line = tag_lines(generic.read_text(), tag)
        tags.add(tag)
        defines.append(define_line)
        enums.append(enum_line)
        applied.append(generic.name)

    if not applied:
        print("Ralink DSA compatibility fix: generic patches absent, skipping")
        return 0

    original = patch.read_text()
    head, hunks = split(original)
    touched = 0
    for index, (header, (body, _)) in enumerate(hunks):
        stripped = added = 0
        if any(DEFINE_ANCHOR.match(line) for line in body):
            stripped, added = rebuild(body, DEFINE_ANCHOR, tags, defines)
        elif any(ENUM_ANCHOR.match(line) for line in body):
            stripped, added = rebuild(body, ENUM_ANCHOR, tags, enums)
        else:
            continue
        hunks[index] = (reheader(header, stripped, added), (body, None))
        touched += 1

    if touched == 0:
        raise RuntimeError("Ralink DSA patch carries no RALINK tag hunk; review it")

    text = "".join(head) + "".join(h + "".join(b) for h, (b, _) in hunks)
    if text != original:
        patch.write_text(text)
        print("Refreshed Ralink DSA patch for " + ", ".join(applied))
    else:
        print("Ralink DSA patch already refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(refresh(Path.cwd()))
