#!/bin/bash
# AP8220 1 GiB NAND build checks and release files. Run from the firmware root.
set -euo pipefail
ci_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_root="$(pwd)"
upload="$source_root/upload"

require_config() {
  if [ "${WRT_CONFIG:-}" != 'IPQ807X-AP8220-1G-WIFI-NO' ]; then
    echo '::error::AP8220 device hook invoked for the wrong configuration' >&2
    exit 2
  fi
}

require_config
case "${1:-}" in
  prepare)
    test "$WRT_SOURCE" = 'VIKINGYFY/immortalwrt'
    patch="$ci_root/patches/ap8220-1g-nand.patch"
    git apply --check "$patch"
    git apply "$patch"
    git diff --check
    git diff --stat
    ;;
  lint)
    sh -n "$ci_root/Scripts/Install-AP8220-1G-From-Transition.sh"
    python3 -m py_compile "$ci_root/Scripts/Check-AP8220-1G.py"
    ;;
  configure)
    sed -i '/^CONFIG_TARGET_ROOTFS_INITRAMFS=/d; /^# CONFIG_TARGET_ROOTFS_INITRAMFS is not set$/d; /^CONFIG_TARGET_ROOTFS_SQUASHFS=/d; /^# CONFIG_TARGET_ROOTFS_SQUASHFS is not set$/d' .config
    printf '%s\n' 'CONFIG_TARGET_ROOTFS_INITRAMFS=y' 'CONFIG_TARGET_ROOTFS_SQUASHFS=y' >> .config
    ;;
  verify)
    grep -Eq '^CONFIG_TARGET_DEVICE_qualcommax_ipq807x_DEVICE_aliyun_ap8220=y$' .config || {
      echo '::error::AP8220 device is not selected' >&2
      exit 1
    }
    grep -Eq '^CONFIG_TARGET_ROOTFS_INITRAMFS=y$' .config || {
      echo '::error::AP8220 initramfs output is not enabled' >&2
      exit 1
    }
    grep -Eq '^CONFIG_TARGET_ROOTFS_SQUASHFS=y$' .config || {
      echo '::error::AP8220 squashfs output is not enabled' >&2
      exit 1
    }
    if [ "$WRT_BRANCH" = 'main' ]; then
      for pattern in \
        '^CONFIG_PACKAGE_nss-firmware=y$' \
        '^CONFIG_PACKAGE_kmod-qca-nss-drv=y$' \
        '^CONFIG_PACKAGE_kmod-qca-nss-ecm=y$' \
        '^CONFIG_PACKAGE_kmod-qca-nss-dp=y$' \
        '^CONFIG_PACKAGE_kmod-qca-ssdk=y$'
      do
        if ! grep -Eq "$pattern" .config; then
          echo "::error::NSS is not selected ($pattern). AP8220 main builds require VIKINGYFY/immortalwrt branch main." >&2
          exit 1
        fi
      done
    fi
    ;;
  verify-image)
    python3 "$ci_root/Scripts/Check-AP8220-1G.py" "$source_root/bin/targets/qualcommax/ipq807x/"
    ;;
  package)
    cd "$upload"
    for file in *aliyun_ap8220*; do
      [ -e "$file" ] || continue
      case "$file" in
        *aliyun_ap8220-1g*) continue ;;
      esac
      mv -f -- "$file" "${file/aliyun_ap8220/aliyun_ap8220-1g}"
    done
    cp "$ci_root/Scripts/Install-AP8220-1G-From-Transition.sh" \
      "$ci_root/docs/AP8220-1G-NAND-SETUP-COMPAT.md" .
    rm -f SHA256SUMS.txt
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum -- * > SHA256SUMS.txt
    else
      echo '::warning::sha256sum is unavailable; AP8220 checksums were not generated.'
    fi
    cat > "$source_root/release-body.md" <<EOF
AP8220 1 GiB NAND 固件：4096-byte page / 256-KiB eraseblock。
仅适用 QWRT 1000 MiB + ubi_kernel 24 MiB 布局，实机启动尚待验证。
先用 Initramfs 启动检查 NAND 读取，再按照随包文档安装。
首次安装脚本会清除原 rootfs_data 和配置；不要使用旧过渡网页的“继续”写入流程。
源码：${WRT_REPO} / ${WRT_BRANCH} / ${WRT_HASH}
登录地址：${WRT_IP}
EOF
    printf 'WRT_ARTIFACT_NAME=AP8220-1G-%s\n' "$GITHUB_RUN_ID" >> "$GITHUB_ENV"
    ;;
  *)
    echo "Usage: $0 prepare|lint|configure|verify|verify-image|package" >&2
    exit 2
    ;;
esac
