#!/bin/bash
# WRT_THEME=auto 时，实时抓取 VIKINGYFY 上游当前使用的默认主题。
#
# 用法：eval "$(bash Scripts/Theme.sh)"
#   - 日志走 stderr，stdout 只输出一行 export 语句，供 eval 注入当前 shell
#   - 同时写入 $GITHUB_ENV，让后续步骤也能拿到
set -euo pipefail

if [ "${WRT_THEME:-}" != 'auto' ]; then
	exit 0
fi

UPSTREAM_WORKFLOW="https://raw.githubusercontent.com/VIKINGYFY/OpenWRT-CI/main/.github/workflows/QCA-ALL.yml"
FALLBACK_THEME="vantage"

resolved="$(curl -fsSL --retry 3 --retry-delay 2 --max-time 30 "$UPSTREAM_WORKFLOW" 2>/dev/null \
	| sed -nE 's/^[[:space:]]*WRT_THEME:[[:space:]]*"?([A-Za-z0-9_.-]+)"?[[:space:]]*$/\1/p' \
	| head -n1 || true)"

if [ -z "$resolved" ]; then
	echo "::warning::could not read WRT_THEME from VIKINGYFY upstream, falling back to $FALLBACK_THEME" >&2
	resolved="$FALLBACK_THEME"
fi

case "$resolved" in
	*[!A-Za-z0-9._-]*)
		echo "::error::upstream WRT_THEME '$resolved' is not a valid theme name" >&2
		exit 1 ;;
esac

echo "theme: auto -> $resolved (from VIKINGYFY/OpenWRT-CI)" >&2
if [ -n "${GITHUB_ENV:-}" ]; then
	printf 'WRT_THEME=%s\n' "$resolved" >> "$GITHUB_ENV"
fi
printf "export WRT_THEME='%s'\n" "$resolved"
