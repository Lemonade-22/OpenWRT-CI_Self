#!/bin/bash
# 固件源码根目录下调用：configure 在 make defconfig 之前，verify 在其之后。
# 本地手工/脚本化构建也要照抄这两步，否则 static-gw 不会进固件。
set -euo pipefail

symbol=CONFIG_PACKAGE_luci-app-static-gw
package_dir=package/luci-app-static-gw
repo=https://github.com/Lemonade-22/luci-app-static-gw.git

usage() {
  echo "Usage: $0 {configure|verify}" >&2
  exit 2
}

# 必须在 buildroot 根目录（./wrt）里跑。跑错位置时 sed -i 会静默新建一个空 .config，
# 看起来"成功"，实际什么都没接上——这类静默跳过正是 static-gw 从固件里消失的成因。
guard_source_root() {
  if [ ! -f rules.mk ] || [ ! -d package ]; then
    echo "::error::Static-Gateway.sh must run from the firmware source root (cwd: $PWD)" >&2
    exit 2
  fi
}

configure() {
  guard_source_root
  # 种子必须先落盘：configure 只负责"clone + 强制选中"，不负责生成 .config。
  [ -f .config ] || {
    echo "::error::no .config in $PWD; apply the config seed before Static-Gateway.sh configure" >&2
    exit 1
  }

  rm -rf "$package_dir"
  git clone --depth=1 --single-branch --branch main "$repo" "$package_dir"
  [ -f "$package_dir/Makefile" ] || {
    echo "::error::luci-app-static-gw checkout has no Makefile; the clone did not land in $package_dir" >&2
    exit 1
  }
  echo "luci-app-static-gw source: $(git -C "$package_dir" rev-parse HEAD)"

  sed -i -E "/^(# )?${symbol}(=| )/d" .config
  printf '%s\n' "${symbol}=y" >> .config
}

verify() {
  guard_source_root
  # 源码树和解析后的 .config 都要查：包目录缺失时 defconfig 会静默丢掉这个符号，
  # 只查 .config 会把"根本没 clone"误判成"配置被改坏"。
  [ -f "$package_dir/Makefile" ] || {
    echo "::error::$package_dir is missing; Static-Gateway.sh configure never ran in this tree" >&2
    exit 1
  }
  grep -qxF "${symbol}=y" .config || {
    echo "::error::luci-app-static-gw is not built into the resolved firmware configuration" >&2
    exit 1
  }
}

case "${1:-}" in
  configure) configure ;;
  verify) verify ;;
  *) usage ;;
esac
