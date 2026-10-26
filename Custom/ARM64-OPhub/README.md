# ARM64：Panther X2 与 Fine3399 的共用 OPhub 构建方案

## 构建入口

Actions → **ARM64-ALL** → Run workflow → `device`：

- `all`：一次内核构建、一次 rootfs 构建，分别打包 Panther X2 和 Fine3399。
- `panther-x2`：只打包 Panther X2。
- `fine3399`：只打包 Fine3399。

原 `Panther-X2-OPhub-OWRT` 入口保留为兼容入口，内部调用同一个 core。
推送相关文件和 PR 只运行 `ARM64 OPhub checks`；手动运行构建入口才编译、打包并发布正式 Release。

## 引用结构

```text
ARM64-ALL.yml（all / panther-x2 / fine3399） ─┐
Panther-X2-OPhub-OWRT.yml（兼容入口）       ─┴→ ARM64-OPhub-CORE.yml
                                                ├─ plan：共用验证 action，输出设备矩阵
                                                ├─ kernel：共用内核、modules、DTBs
                                                ├─ rootfs：共用 armsr/armv8 用户空间
                                                └─ package：按设备矩阵独立打包和发布
ARM64-CHECK.yml → .github/actions/arm64-ophub-validate/action.yml
```

`kernel` 与 `rootfs` 在 plan 通过后并行运行；package 等待两者成功。矩阵中的设备各有独立工作目录、Artifact 和 Release，一台打包失败不取消另一台。两个构建入口使用相同并发组，避免重复提交同一分支的 Arm64 构建。

| 位置 | 职责 |
| --- | --- |
| `.github/workflows/ARM64-ALL.yml` | 用户设备选择入口 |
| `.github/workflows/ARM64-OPhub-CORE.yml` | 内核、rootfs、打包、发布的唯一实现 |
| `.github/actions/arm64-ophub-validate/action.yml` | 检查和构建复用的依赖、设备表、引导文件验证 |
| `Custom/ARM64-OPhub/devices.json` | 设备名、SoC、DTB、引导文件、分区容量和 Release 前缀 |
| `Custom/ARM64-OPhub/sources.json` | 共用的固定资源提交及内核参数 |
| `Custom/ARM64-OPhub/profiles.py` | 选择设备、核对上游设备表并生成矩阵 |
| `Custom/ARM64-OPhub/{pin_ophub,prepare_kernel,stage_kernel}.py` | 原 Panther 实现移入共用目录 |
| `Config/ARM64-OPhub.txt` | 两台设备共用的 generic ARM64 rootfs 配置 |
| `Scripts/Check-DAEDE-Kernel.py` | 最终外部内核的 BTF、eBPF、模块和所选设备 DTB 检查 |

`WRT-CORE.yml` 仍归上游维护，`WRT-CORE-SELF.yml` 仍通过补丁生成，供原生 OpenWrt target 使用。ARM64 OPhub core 复用本仓库 DAEDE/Fakeflow 脚本，但独立负责外部内核与整盘镜像打包，避免将 OPhub 设备步骤塞入上游补丁。

## 设备规格与证据

| 项目 | Panther X2 | Fine3399 |
| --- | --- | --- |
| OPhub board | `panther-x2` | `fine3399` |
| SoC | RK3566 | RK3399 |
| DTB | `rk3566-panther-x2.dtb` | `rk3399-fine3399.dtb` |
| 引导组合 | `idbloader.img` + `u-boot.itb` | `idbloader.bin` + `uboot.img` + `trust.bin` |
| 引导配置 | `armbianEnv.txt`，沿用 OPhub 启动资源 | 相同机制，使用 Fine3399 专属 DTB |
| 用户空间 | `VIKINGYFY/immortalwrt:owrt`，`armsr/armv8` generic | 共用同一 rootfs |
| 外部内核 | 自编译 OPhub stable 6.18.51 | 共用同一内核和模块包，检查自己的 DTB |
| BOOT / ROOTFS | 384 / 1280 MiB，保留原方案 | 沿用共用方案 384 / 1280 MiB |
| 输出 | 独立 `*panther-x2*.img.gz` | 独立 `*fine3399*.img.gz` |
| Release 前缀 | `Panther-X2-OPhub-OWRT`，保留原命名 | `Fine3399-OPhub-OWRT` |

核查基准（2026-10-26）：

- [OPhub 固定设备表](https://github.com/ophub/amlogic-s9xxx-openwrt/blob/028c444dbdb74b1d005affc707cb4cf8adc922a1/make-openwrt/openwrt-files/common-files/etc/model_database.conf)：r301 和 r416 均支持 stable/6.18.y。Fine3399 条目列出 4GB RAM、8/16/64/128GB eMMC、TF 和千兆网口；这是上游设备描述，未作为用户实际硬件容量的确认。
- [固定 U-Boot 资源](https://github.com/ophub/u-boot/tree/6d28887796f8e757d7e5f6d7517d7dcb401be1a0/u-boot/rockchip/fine3399)：上述三个 Fine3399 文件均存在。Panther 专用文件位于同提交 `panther-x2/`。
- [Fine3399 来源说明](https://github.com/ophub/amlogic-s9xxx-armbian/issues/1790)：该板使用 SW799 系列核心板，OPhub 已有 Fine3399 独立设备支持。
- [OPhub 6.18 Fine3399 DTS](https://github.com/ophub/linux-6.18.y/blob/794930c6844d1fc83990deffcdd787d37df120a0/arch/arm64/boot/dts/rockchip/rk3399-fine3399.dts) 继承 `rk3399.dtsi`；同提交 Makefile 包含两台设备的 DTB 构建项。该提交用于本次源码核查，构建器仍沿用既有 `kernel_source: ophub` 获取机制，不宣称源码完全冻结。
- [固定内核配置](https://github.com/Lemonade-22/ophub-kernel/blob/35527918391e697f994d9efa02948d4308a7a766/kernel-config/release/stable/config-6.18) 已启用 ARCH_ROCKCHIP、DWMAC_ROCKCHIP、MMC_DW_ROCKCHIP、MMC_SDHCI_OF_ARASAN、RK808 电源管理和 Rockchip PCIe/NVMe 支持。prepare_kernel.py 保留硬件配置，只补 BTF/eBPF/fake-flow 需求。

因此本方案复用 OPhub 已有板级支持，无需从另一套内核移植 DTS，也不将 Panther DTB 改名给 Fine3399 使用。最终内核包缺少任一所选设备 DTB，或缺少所需模块时，打包前直接失败。

## 共用依赖与插件

沿用 Panther 的固定打包器 `028c444dbdb74b1d005affc707cb4cf8adc922a1`，资源锁完整保存在 sources.json，包括 U-Boot、Armbian 启动资源、firmware 和 luci-app-amlogic。此次归类不升级依赖版本。

内核模板从 `Lemonade-22/ophub-kernel` 的固定提交读取，固定版本的 OPhub 编译工具构建内核、模块和 DTBs。配置文件系列从内核版本推导。由于 GitHub Actions 的 `uses` 不能使用动态表达式，编译工具 SHA 同时存在于 workflow 和 sources.json；自动测试核对两者一致。

插件沿用 Panther：每次获取 VIKINGYFY/OpenWRT-CI main 的 GENERAL.txt、Packages.sh、Handles.sh、Settings.sh，主题读取同一快照的 OWRT-ALL.yml；记录上游实际提交。随后应用共用 ARM64 配置，再运行 DAEDE 和 Fakeflow 配置及检查。构建核对上游默认选中的 LuCI 插件没有被 defconfig 丢弃。本次不额外改变插件集合。

OPhub 会替换 rootfs 原有内核模块，OpenWrt rootfs 配置不能证明最终内核的驱动或硬件加速能力。BTF/eBPF 和 fake-flow 同时检查最终内核配置与实际模块文件。Docker 镜像、工具链、内核下载机制沿用 Panther 的现状，不宣称整个构建完全可复现。

## 产物与验证

同次构建先保存 `arm64-ophub-kernel` 和 `arm64-ophub-rootfs`，然后各设备独立下载并校验 SHA256。每台设备的发布文件包含镜像、rootfs、内核请求配置、依赖锁、设备表、插件配置快照、源码和 feeds 提交、引导文件校验值、build-info.txt、SHA256SUMS。

- 本地检查：设备矩阵、固定设备表/引导文件核对、内核 DTB 和模块缺失的拒绝路径、内核包暂存、Actions 语法。
- 云端 `ARM64 OPhub checks`：再次获取固定资源，验证下载接入和 shell 语法并运行测试。
- 首次手动构建：确认两份 DTB、镜像、各自引导校验及发布产物。
- Fine3399 实机：确认实际核心板/底板版本和存储容量；验证启动、网口、TF/eMMC、USB、所需 PCIe/NVMe、温控及 dae/daed/fake-flow。Wi-Fi、蓝牙和屏幕是否适用及可用按具体硬件测试。

Panther 旧版 `2026.09.17-10.44.03` 有维护者确认可用的历史记录；这不代表新共用 core 或 Fine3399 已通过实机验证。当前改动交付到移植方案与构建结构，不自动触发数小时固件编译。

镜像是压缩的整盘 `.img.gz`，应按 OPhub 对应设备安装流程使用，不能当作 OpenWrt 原生 sysupgrade 镜像。默认 LAN 地址沿用 `192.168.10.1`；账号密码以最终 rootfs/OPhub 设置为准。

## 维护

设备差异改 devices.json；共用 rootfs 选项改 Config/ARM64-OPhub.txt；依赖更新改 sources.json 并重跑 ARM64 OPhub checks。涉及内核 builder 更新时同步 workflow 的固定 SHA。若以后设备需要不同内核系列或用户空间，再拆分对应构建组；目前两台均使用同一个 stable 配置。

上游 CI 同步仍由 sync-upstream.yml 处理，共用 Arm64 core 不进入 wrt-core-self.patch。若同步涉及 workflow 文件而默认 GITHUB_TOKEN 无法推送，仓库的 `UPSTREAM_SYNC_TOKEN` 需具有该仓库内容及 workflow 写入权限；同步脚本已有该 Secret 的优先使用逻辑。
