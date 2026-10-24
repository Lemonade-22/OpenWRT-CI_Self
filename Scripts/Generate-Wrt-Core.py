#!/usr/bin/env python3
"""Generate common and AP8220 workflows from upstream plus layered patches."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check the committed workflows without writing them')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = Path('.github/workflows/WRT-CORE.yml')
    variants = (
        ('wrt-core-self.patch', 'WRT-CORE-SELF.yml'),
        ('wrt-core-ap8220.patch', 'AP8220-CORE.yml'),
    )
    generated = {}

    with tempfile.TemporaryDirectory(prefix='wrt-core-') as directory:
        staged = Path(directory) / source
        staged.parent.mkdir(parents=True)
        staged.write_text((root / source).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        for patch_name, workflow in variants:
            patch = root / 'patches' / patch_name
            try:
                subprocess.run(
                    ['git', '-c', 'core.autocrlf=false', 'apply', '--no-index', '--whitespace=error', str(patch)],
                    cwd=directory, check=True,
                )
            except subprocess.CalledProcessError:
                print(f'::error::{patch_name} conflicts with WRT-CORE.yml or its preceding patch. Update the patch before syncing upstream.')
                return 1
            generated[root / '.github/workflows' / workflow] = staged.read_text(encoding='utf-8')

    if args.check:
        stale = [output.name for output, content in generated.items()
                 if not output.exists() or output.read_text(encoding='utf-8') != content]
        if stale:
            for name in stale:
                print(f'::error::{name} is stale. Run python3 Scripts/Generate-Wrt-Core.py and commit the result.')
            return 1
        print('Both generated workflows match upstream plus their local patches.')
    else:
        # Finish applying both patches before replacing either committed workflow.
        for output, content in generated.items():
            output.write_text(content, encoding='utf-8', newline='\n')
            print(f'Generated .github/workflows/{output.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
