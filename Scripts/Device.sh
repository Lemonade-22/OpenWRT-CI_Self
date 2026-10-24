#!/bin/bash
# Optional per-device hooks. A missing hook is a successful no-op.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${WRT_CONFIG:?WRT_CONFIG required}"
if [[ "$WRT_CONFIG" == *[!A-Za-z0-9._-]* || "$WRT_CONFIG" == *..* ]]; then
  echo "::error::Invalid WRT_CONFIG for device hook: $WRT_CONFIG" >&2
  exit 2
fi
hook="$ci_root/Scripts/Device-Hooks/$WRT_CONFIG.sh"
if [ ! -f "$hook" ]; then
  exit 0
fi
"${BASH:-bash}" "$hook" "$@"
