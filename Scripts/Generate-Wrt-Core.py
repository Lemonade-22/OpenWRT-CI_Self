#!/usr/bin/env python3
"""Generate the custom workflow from upstream plus its local patch."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check the committed workflow without writing it')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = Path('.github/workflows/WRT-CORE.yml')
    output = root / '.github/workflows/WRT-CORE-SELF.yml'
    patch = root / 'patches/wrt-core-self.patch'

    with tempfile.TemporaryDirectory(prefix='wrt-core-') as directory:
        staged = Path(directory) / source
        staged.parent.mkdir(parents=True)
        staged.write_text((root / source).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        try:
            subprocess.run(
                ['git', '-c', 'core.autocrlf=false', 'apply', '--no-index', '--whitespace=error', str(patch)],
                cwd=directory, check=True,
            )
        except subprocess.CalledProcessError:
            print('::error::wrt-core-self.patch conflicts with WRT-CORE.yml. Update the patch before syncing upstream.')
            return 1
        generated = staged.read_text(encoding='utf-8')

    if args.check:
        if not output.exists() or output.read_text(encoding='utf-8') != generated:
            print('::error::WRT-CORE-SELF.yml is stale. Run python3 Scripts/Generate-Wrt-Core.py and commit the result.')
            return 1
        print('WRT-CORE-SELF.yml matches upstream plus the local patch.')
    else:
        output.write_text(generated, encoding='utf-8', newline='\n')
        print('Generated .github/workflows/WRT-CORE-SELF.yml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
