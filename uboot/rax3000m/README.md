# RAX3000M (NAND) U-Boot —— Yuzhii ubootmod

> Web UI + 自动 DHCP + 支持 fitblk 固件（root=/dev/fit0）

## 固件概览

| 项目 | 值 |
|---|---|
| 版本 | U-Boot 2025.07.1-Mediatek，VERSION=SP2，VARIANT=ubootmod |
| 源码 | Yuzhii0718/bl-mt798x-dhcpd（hanwckf/bl-mt798x 的分支） |
| 特性 | failsafe Web UI、内置 DHCPD、网页刷固件/刷 FIP/写 factory/备份/网页控制台 |
| 适用设备 | CMCC RAX3000M（SPI-NAND，128 MiB） |

## 文件

| 文件 | 大小 | MD5 | 说明 |
|---|---|---|---|
| fip-mt7981_cmcc_rax3000m_SP2-Yuzhii-dhcpd-fit-114M.bin | 914,640 B | 17fce17c10ad2e8d15c13b5c140bfcd8 | U-Boot FIP，写入 fip 分区 |
| bl2-mt7981_cmcc_rax3000m_SP2-fit.img | 172,544 B | da76edae1f77398c3501f7e215923326 | ATF BL2，写入 bl2 分区 |

> 本次只刷了 FIP，BL2 保留原机（VIKINGYFY nand preloader），两者可共存并正常引导。BL2 文件一并留档，仅在 BL2 损坏时使用。

## 本机分区布局（刷前必须一致）

```
bl2         0x000000 - 0x100000   1 MiB
u-boot-env  0x100000 - 0x180000   512 KiB
factory     0x180000 - 0x380000   2 MiB
fip         0x380000 - 0x580000   2 MiB
ubi         0x580000 - 0x7780000  114 MiB
```

## 编译环境（WSL Ubuntu 24.04，root）

### 1. 安装依赖

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get install -y build-essential gcc-aarch64-linux-gnu flex bison libssl-dev \
  device-tree-compiler swig python3-dev python3-setuptools u-boot-tools bc \
  nodejs npm
```

两个容易漏的依赖：

- **npm**：构建 failsafe Web UI 需要；缺了会直接报 `npm is not installed`
- **python**：ATF 编译脚本调用的是 `python` 而不是 `python3`，Ubuntu 24.04 默认没有该名字

```bash
ln -sf /usr/bin/python3 /usr/bin/python
```

### 2. 拉取源码并编译

```bash
git clone https://github.com/Yuzhii0718/bl-mt798x-dhcpd.git
cd bl-mt798x-dhcpd
make BOARD=cmcc_rax3000m VARIANT=ubootmod VERSION=SP2 -j8
```

产物在 `output/`。

## 关键修改（必须，否则刷完起不来）

文件：`uboot-mtk-20250711/configs-fit/mt7981_cmcc_rax3000m_defconfig`

```diff
- CONFIG_MTDPARTS_DEFAULT="spi-nand0:1024k(bl2),512k(u-boot-env),2048k(factory),2048k(fip),-(ubi)"
+ CONFIG_MTDPARTS_DEFAULT="spi-nand0:1024k(bl2),512k(u-boot-env),2048k(factory),2048k(fip),114M(ubi)"
```

### 为什么必须改

`-(ubi)` 表示"剩余空间全部给 ubi"，即 `128 MiB - 5.5 MiB = 122.5 MiB`，建出来的 UBI 是 **980 个 PEB**。

而固件设备树（`mt7981b-cmcc-rax3000m.dts` 的 `nand` overlay）把 ubi 写死为 **114 MiB，912 个 PEB**。

于是内核挂载时报错：

```
ubi0 error: ubi_read_volume_table: not enough PEBs, required 958, available 912
ubi0 error: ubi_attach_mtd_dev: failed to attach mtd0, error -28
platform fitblk: deferred probe pending
```

UBI 挂不上 → 没有 `ubiblock0_2` → 没有 `/dev/fit0` → 内核永远停在 `Waiting for root device /dev/fit0...`。

上游其他变体（`configs/`、`configs-nonmbm/`）本来就写的是 `114M(ubi)`，只有 `configs-fit/` 这一条漏了尺寸。改掉即与其他变体一致。

## 使用方式

1. 断电
2. **按住 RESET 不放**
3. 上电，数到 5 秒松手
4. 电脑保持 DHCP 自动获取（U-Boot 会下发 `192.168.1.x`）
5. 浏览器打开 http://192.168.1.1

| 页面 | 作用 |
|---|---|
| `/` | 刷固件（上传 `.itb`） |
| `/uboot.html` | 刷 U-Boot FIP |
| `/initramfs.html` | 加载内存系统 |
| `/factory.html` | 写入 RF / factory 数据 |
| `/backup.html` | 备份分区或指定范围 |
| `/flash.html` | 原始 flash 读/写/擦 |
| `/console.html` | 网页 U-Boot 控制台 |

## 验证清单

刷完 U-Boot 后，在 `/console.html` 执行 `printenv mtdparts`，**必须**包含 `114M(ubi)`。若显示 `-(ubi)`，说明用的还是旧 FIP。

刷完固件进入系统后：

```bash
cat /proc/mtd            # mtd0 ubi 应为 07200000（114 MiB）
ubinfo | grep -i peb     # 应为 912
iwinfo                   # WIFI-YES 固件应有无线
ip -br link show eth0    # MAC 应为原机地址，而非随机地址
```
