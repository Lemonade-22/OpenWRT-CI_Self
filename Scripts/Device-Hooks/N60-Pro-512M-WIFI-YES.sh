#!/bin/bash
# N60 Pro 512M —— WIFI-YES。分区与产物逻辑沿用 WIFI-NO 那份钩子，
# 两个版本只差配置包里是否关闭 mt76 无线包。
set -euo pipefail
exec bash "$(dirname "$0")/N60-Pro-512M-WIFI-NO.sh" "$@"
