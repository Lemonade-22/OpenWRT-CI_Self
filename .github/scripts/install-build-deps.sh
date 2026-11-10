#!/bin/bash
# SPDX-License-Identifier: MIT
#
# Install the host packages the immortalwrt build needs.
#
# This replaces upstream's init_build_environment.sh, which refuses any Ubuntu
# whose VERSION_CODENAME is missing from a hardcoded case list. ubuntu-latest
# now lands on 26.04 ("resolute") and that script exits with
# "Unsupported OS, use Ubuntu 20.04 instead." before installing anything.
# Installing from the distribution instead keeps the workflows working across
# the 24.04 -> 26.04 migration without pinning a runner image, and drops the
# parts of that script we do not need (toolchain PPAs, golang, upx, po2lmo).

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_SUSPEND=1

# Recommends reach the whole TeX Live stack through xmlto; on a shared mirror
# that alone can stall this step for an hour.
echo 'APT::Install-Recommends "false";
APT::Install-Suggests "false";
Acquire::Retries "3";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";' | tee /etc/apt/apt.conf.d/99-wrt-norecommends >/dev/null

apt-get update -qq

apt-get install -y -qq --no-install-recommends \
	bc bison build-essential bzip2 ca-certificates ccache clang \
	cmake cpio curl device-tree-compiler dos2unix file flex \
	g++-multilib gawk gcc-multilib genisoimage gettext git jq \
	libbpf-dev libclang-dev libdw-dev libelf-dev libfuse-dev libncurses-dev libssl-dev lld \
	llvm ninja-build patch perl pkgconf python3 python3-cryptography \
	python3-dev python3-packaging python3-pyelftools python3-setuptools qemu-utils rsync swig \
	unzip wget xz-utils zlib1g-dev zstd

# Buildroot's toolchain build expects a stable c++ link and /usr/include/asm;
# Ubuntu provides neither by default.
ln -sfv /usr/bin/g++ /usr/bin/c++
[ -e /usr/include/asm ] || ln -sfv "/usr/include/$(gcc -dumpmachine)/asm" /usr/include/asm

. /etc/os-release
echo "--- build dependencies installed on ${PRETTY_NAME} ---"
gcc --version | head -1
clang --version | head -1
