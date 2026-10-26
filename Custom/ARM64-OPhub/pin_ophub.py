#!/usr/bin/env python3
"""Pin ophub dependency downloads without changing its board/image recipe."""
import json
from pathlib import Path
import re
import sys

here = Path(__file__).resolve().parent
lock = json.loads((here / 'sources.json').read_text(encoding='utf-8'))
source = Path(sys.argv[1])
text = source.read_text(encoding='utf-8')
assert all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in lock['repositories'].values())
assert lock['kernel']['mode'] == 'build'
assert re.fullmatch(r'[0-9a-f]{40}', lock['kernel']['config_commit'])
assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', lock['kernel']['version'])
cases = '\n'.join('        "' + repo + '") locked_commit="' + sha + '" ;;'
                  for repo, sha in lock['repositories'].items())
replacement = '''git_pull_dir() {
    local git_repo="${1}" git_path="${3}" locked_commit
    case "${git_repo}" in
CASES
        *) error_msg "Unpinned dependency repository: ${git_repo}" ;;
    esac
    git init --quiet "${git_path}" || error_msg "Cannot initialize dependency checkout"
    git -C "${git_path}" remote add origin "${git_repo}" || error_msg "Cannot configure dependency remote"
    local fetched=0
    for attempt in 1 2 3; do
        if git -C "${git_path}" fetch --quiet --depth=1 origin "${locked_commit}"; then
            fetched=1
            break
        fi
        sleep 3
    done
    [[ "${fetched}" == 1 ]] || error_msg "Cannot fetch pinned dependency ${git_repo}"
    git -C "${git_path}" checkout --quiet --detach FETCH_HEAD || error_msg "Cannot checkout dependency"
    [[ "$(git -C "${git_path}" rev-parse HEAD)" == "${locked_commit}" ]] || error_msg "Dependency commit mismatch"
}
'''.replace('CASES', cases)
pattern = r'^git_pull_dir\(\) \{\n.*?^\}\n'
assert len(re.findall(pattern, text, re.M | re.S)) == 1, 'Unexpected ophub downloader structure'
updated = re.sub(pattern, lambda _: replacement, text, count=1, flags=re.M | re.S)
# Reject added/untracked dependency repositories before patching anything.
repos = set(re.findall(r'^\w+_repo="(https://github.com/[^" ]+)"', text, re.M))
assert repos - {'https://github.com/ophub/kernel'} == set(lock['repositories']), repos
# A missing artifact must never fall back to an unrelated release kernel.
kernel_pattern = r'^download_kernel\(\) \{\n.*?^\}\n'
assert len(re.findall(kernel_pattern, updated, re.M | re.S)) == 1
local_kernel = 'download_kernel() {\n    [[ -d "${kernel_path}/stable/VERSION" ]] || error_msg "Compiled kernel artifact missing; refusing remote fallback"\n}\n'.replace('VERSION', lock['kernel']['version'])
updated = re.sub(kernel_pattern, lambda _: local_kernel, updated, count=1, flags=re.M | re.S)
source.write_text(updated, encoding='utf-8', newline='\n')
print('Pinned four ophub resource repositories; board and image logic unchanged.')
