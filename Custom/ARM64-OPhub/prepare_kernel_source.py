#!/usr/bin/env python3
"""Prepare the pinned ophub kernel source checkout and apply the SONiC fullcone patches."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SOURCES = Path(__file__).with_name("sources.json")
LOCAL_PATCH = (Path(__file__).with_name("patches") / "987-fix-ophub-fullcone-attributes.patch").resolve()
BRIDGE_PATCH_DIR = (Path(__file__).with_name("patches") / "bridge-flowtable").resolve()

# Explicit source markers written by the three SONiC kernel patches. The marker
# files are part of the pinned kernel source, so their presence identifies an
# already-patched tree without trusting .rej files or a stale git index.
MARKERS = (
    ("include/uapi/linux/netfilter/nf_nat.h", ("NF_NAT_RANGE_FULLCONE",)),
    ("net/netfilter/xt_MASQUERADE.c", ('"FULLCONE"',)),
    ("net/netfilter/nft_masq.c", ("nft_fullcone_type", '"fullcone"')),
)


class SourcePreparationError(RuntimeError):
    """A pinned kernel source checkout or SONiC patch application cannot proceed."""


def load_lock():
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def _git(*arguments, error=None):
    command = ["git", *[str(argument) for argument in arguments]]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError as exception:
        raise SourcePreparationError("git is not available: " + str(exception)) from exception
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SourcePreparationError((error or "git command failed") + (": " + detail if detail else ""))
    return result.stdout


def checkout_head(path):
    return _git("-C", path, "rev-parse", "HEAD",
                error=f"{path} is not a git checkout").strip()


def verify_checkout(path, commit, label):
    actual = checkout_head(path)
    if actual != commit:
        raise SourcePreparationError(
            f"{label} checkout {path} is at {actual}, expected {commit}; refusing to continue"
        )
    return actual


def marker_state(destination):
    """Return the applied state of each explicit SONiC patch marker in destination."""
    states = []
    for relative, needles in MARKERS:
        path = Path(destination) / relative
        if not path.is_file():
            states.append(False)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        states.append(any(needle in text for needle in needles))
    return states


def describe_markers(states):
    return ", ".join(
        f"{relative}={'applied' if state else 'missing'}"
        for (relative, _), state in zip(MARKERS, states)
    )


def ensure_destination(destination, source_repository, source_commit):
    """Create the pinned kernel checkout when absent; otherwise prove its HEAD."""
    destination = Path(destination)
    if destination.exists():
        if destination.is_dir() and not any(destination.iterdir()):
            pass  # An empty directory is safe to initialize in place.
        else:
            return verify_checkout(destination, source_commit, "Kernel source")
    destination.mkdir(parents=True, exist_ok=True)
    _git("init", "--quiet", destination, error="Cannot create the pinned kernel source checkout")
    _git("-C", destination, "remote", "add", "origin", source_repository,
         error="Cannot register the pinned kernel source repository")
    _git("-C", destination, "fetch", "--depth=1", "origin", source_commit,
         error="Cannot fetch the pinned kernel source commit " + source_commit)
    _git("-C", destination, "checkout", "--quiet", "--detach", "FETCH_HEAD",
         error="Cannot check out the pinned kernel source commit " + source_commit)
    return verify_checkout(destination, source_commit, "Kernel source")


def patch_files(patch_root, patches, label="SONiC kernel"):
    files = []
    for relative in patches:
        path = Path(patch_root) / relative
        if not path.is_file():
            raise SourcePreparationError(
                f"{label} patch is missing from {patch_root}: {relative}"
            )
        files.append(path)
    return files


def _apply_patch(destination, patch, label="SONiC kernel"):
    _git("-C", destination, "apply", "--check", patch,
         error=f"{label} patch does not apply: {patch.name}")
    _git("-C", destination, "apply", patch,
         error=f"Cannot apply {label} patch: {patch.name}")


def apply_ophub_compatibility(destination, check=False):
    """Apply the attribute translation, including to previously prepared trees."""
    reverse = subprocess.run(
        ["git", "-C", str(destination), "apply", "--reverse", "--check", str(LOCAL_PATCH)],
        capture_output=True, text=True)
    if reverse.returncode == 0:
        return
    if check:
        _git("-C", destination, "apply", "--check", LOCAL_PATCH,
             error="OPhub fullcone compatibility patch does not apply")
    else:
        _apply_patch(destination, LOCAL_PATCH)


def bridge_marker_state(destination, bridge):
    """Return whether the pinned bridge flowtable implementation is present."""
    if not bridge:
        return False
    marker_file = Path(destination) / bridge["marker_file"]
    if not marker_file.is_file():
        return False
    return bridge["marker"] in marker_file.read_text(encoding="utf-8", errors="replace")


def _patch_is_applied(destination, patch):
    result = subprocess.run(
        ["git", "-C", str(destination), "apply", "--reverse", "--check", str(patch)],
        capture_output=True, text=True)
    return result.returncode == 0


def apply_bridge_flowtable(destination, bridge, check=False):
    """Apply the pinned bridge-family flowtable support used by fw4."""
    if not bridge:
        return False
    marker_file = Path(destination) / bridge["marker_file"]
    if not marker_file.is_file():
        # Unit-test fixtures and other partial trees cannot carry this series.
        print("Skipping bridge flowtable patches: missing", marker_file)
        return False
    if bridge_marker_state(destination, bridge):
        print("Kernel source already contains bridge flowtable support; skipping idempotently")
        return True

    patches = patch_files(BRIDGE_PATCH_DIR, bridge["patches"], label="Bridge flowtable")
    for patch in patches:
        if _patch_is_applied(destination, patch):
            continue
        if check:
            _git("-C", destination, "apply", "--check", patch,
                 error=f"Bridge flowtable patch does not apply: {patch.name}")
        else:
            _apply_patch(destination, patch, label="Bridge flowtable")
            print("Applied bridge flowtable patch:", patch.name)

    if not bridge_marker_state(destination, bridge):
        raise SourcePreparationError(
            "Kernel source is missing the bridge flowtable marker after applying patches"
        )
    return True


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(patch_root, destination, lock=None, check=False, record=None):
    """Prepare destination and apply the locked SONiC patches; return the record when applying."""
    lock = lock if lock is not None else load_lock()
    userspace = lock["userspace"]
    bridge = lock.get("bridge_flowtable")
    kernel = lock["kernel"]
    patch_root = Path(patch_root).resolve()
    destination = Path(destination).resolve()

    verify_checkout(patch_root, userspace["commit"], "SONiC patch root")
    patches = patch_files(patch_root, userspace["kernel_patches"])

    if check:
        if not destination.exists():
            raise SourcePreparationError(
                f"--check requires an existing kernel source checkout: {destination}"
            )
        verify_checkout(destination, kernel["source_commit"], "Kernel source")
        states = marker_state(destination)
        if any(states) and not all(states):
            raise SourcePreparationError("Kernel source is partially patched: " + describe_markers(states))
        if all(states):
            apply_ophub_compatibility(destination, check=True)
            apply_bridge_flowtable(destination, bridge, check=True)
            print("Checked SONiC patches and OPhub attribute compatibility")
            return None
        for patch in patches:
            _git("-C", destination, "apply", "--check", patch,
                 error=f"SONiC kernel patch does not apply: {patch.name}")
        print("Checked SONiC kernel patches:", ", ".join(patch.name for patch in patches))
        return None

    ensure_destination(destination, kernel["source_repository"], kernel["source_commit"])
    states = marker_state(destination)
    if all(states):
        print("Kernel source already contains the SONiC fullcone patches; skipping idempotently")
    elif any(states):
        raise SourcePreparationError("Kernel source is partially patched: " + describe_markers(states))
    else:
        for patch in patches:
            _apply_patch(destination, patch)
            print("Applied SONiC kernel patch:", patch.name)

    apply_ophub_compatibility(destination)
    bridge_applied = apply_bridge_flowtable(destination, bridge)
    final_states = marker_state(destination)
    if not all(final_states):
        raise SourcePreparationError(
            "Kernel source is missing SONiC fullcone markers after applying patches: "
            + describe_markers(final_states)
        )
    diff = _git("-C", destination, "diff")
    result = {
        "source_repository": kernel["source_repository"],
        "source_commit": kernel["source_commit"],
        "userspace_commit": userspace["commit"],
        "patches": [{"path": relative, "sha256": _sha256(Path(patch_root) / relative)}
                    for relative in userspace["kernel_patches"]],
        "compatibility_patches": [{"path": LOCAL_PATCH.name, "sha256": _sha256(LOCAL_PATCH)}],
        "bridge_flowtable_applied": bridge_applied,
        "bridge_flowtable_patches": ([
            {"path": relative, "sha256": _sha256(BRIDGE_PATCH_DIR / relative)}
            for relative in bridge["patches"]
        ] if bridge else []),
        "applied": True,
        "diff_stat": _git("-C", destination, "diff", "--stat").splitlines(),
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
    }
    if record is not None:
        record = Path(record)
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("Wrote kernel source preparation record:", record)
    print("Kernel source is ready at", destination)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-root", required=True, help="Checkout of the locked userspace kernel patches")
    parser.add_argument("--destination", required=True, help="Checkout of the pinned kernel source")
    parser.add_argument("--record", help="Write a JSON preparation record to this path")
    parser.add_argument("--check", action="store_true",
                        help="Validate the existing checkout and patches only; modify nothing")
    args = parser.parse_args(argv)
    try:
        prepare(args.patch_root, args.destination, check=args.check, record=args.record)
    except SourcePreparationError as error:
        sys.exit("::error::" + str(error))


if __name__ == "__main__":
    main()
