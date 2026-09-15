#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/../Custom/Panther-X2/apply.py" "${1:-${GITHUB_WORKSPACE:?}/wrt}"
