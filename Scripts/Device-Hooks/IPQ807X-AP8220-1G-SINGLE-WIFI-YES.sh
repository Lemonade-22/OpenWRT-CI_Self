#!/bin/bash
# AP8220 1 GiB NAND 单分区变体 —— WIFI-YES。
# 分区、镜像产物与校验全部沿用 WIFI-NO 那份钩子，两者只差配置里的无线开关。
set -euo pipefail
exec bash "$(dirname "$0")/IPQ807X-AP8220-1G-SINGLE-WIFI-NO.sh" "$@"