# ARM64：Panther X2 与 Fine3399 的共用 OPhub 构建方案

## 构建入口

Actions → **ARM64-ALL** → Run workflow → `device`：

- `all`：一次内核构建、一次 rootfs 构建，分别打包 Panther X2 和 Fine3399。
- `panther-x2`：只打包 Panther X2。
- `fine3399`：只打包 Fine3399。

两台设备统一从 `ARM64-ALL` 进入，原 Panther 单独 workflow 已删除。
推送相关文件和 PR 只运行 `ARM64 OPhub checks`；手动运行构建入口才编译、打包并发布正式 Release。

## 引用结构

```text
ARM64-ALL.yml（all / panther-x2 / fine3399） → ARM64-OPhub-CORE.yml
                                                ├─ plan：共用验证 action，输出设备矩阵
                                                ├─ kernel：共用内核、modules、DTBs
                                                ├─ rootfs：共用 armsr/armv8 用户空间
                                                └─ package：按设备矩阵独立打包和发布
ARM64-CHECK.yml → .github/actions/arm64-ophub-validate/action.yml
```

`kernel` 与 `rootfs` 在 plan 通过后并行运行；package 等待两者成功。矩阵中的设备各有独立工作目录、Artifact 和 Release，一台打包失败不取消另一台。统一入口按分支串行调度 Arm64 构建。

| 位置 | 职责 |
| --- | --- |
| `.github/workflows/ARM64-ALL.yml` | 用户设备选择入口 |
| `.github/workflows/ARM64-OPhub-CORE.yml` | 内核、rootfs、打包、发布的唯一实现 |
| `.github/actions/arm64-ophub-validate/action.yml` | 检查和构建复用的依赖、设备表、引导文件、固定源码验证 |
| `Custom/ARM64-OPhub/devices.json` | 设备名、SoC、DTB、引导文件、分区容量和 Release 前缀 |
| `Custom/ARM64-OPhub/sources.json` | 共用固定资源、锁定用户空间提交、内核源码提交和内核参数 |
| `Custom/ARM64-OPhub/profiles.py` | 选择设备、核对上游设备表并生成矩阵 |
| `Custom/ARM64-OPhub/{pin_ophub,prepare_kernel,prepare_kernel_source,stage_kernel}.py` | 固定打包器、内核配置、固定内核源和补丁、产物暂存 |
| `Custom/ARM64-OPhub/verify_packages.py` | 核对 `make defconfig` 后上游选中的 LuCI 插件是否被丢弃 |
| `Custom/ARM64-OPhub/fine3399-direct-lan` | Fine3399 首次启动的 LAN/WAN/DHCP 默认值（仅该设备） |
| `Config/ARM64-OPhub.txt` | 两台设备共用的 generic ARM64 rootfs 配置 |
| `Scripts/Check-DAEDE-Kernel.py` | 最终外部内核的 BTF、eBPF、SONiC、所选设备驱动和 DTB 检查 |

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
| 外部内核 | 自编译 OPhub stable 6.18.59 | 共用同一内核和模块包，检查自己的 DTB |
| BOOT / ROOTFS | 384 / 1280 MiB，保留原方案 | 沿用共用方案 384 / 1280 MiB |
| 输出 | 独立 `*panther-x2*.img.gz` | 独立 `*fine3399*.img.gz` |
| Release 前缀 | `Panther-X2-OPhub-OWRT`，保留原命名 | `Fine3399-OPhub-OWRT` |

核查基准（2026-10-26/27）：

- [OPhub 固定设备表](https://github.com/ophub/amlogic-s9xxx-openwrt/blob/028c444dbdb74b1d005affc707cb4cf8adc922a1/make-openwrt/openwrt-files/common-files/etc/model_database.conf)：r301 和 r416 均支持 stable/6.18.y。Fine3399 条目列出 4GB RAM、8/16/64/128GB eMMC、TF 和千兆网口；这是上游设备描述，未作为用户实际硬件容量的确认。
- [固定 U-Boot 资源](https://github.com/ophub/u-boot/tree/6d28887796f8e757d7e5f6d7517d7dcb401be1a0/u-boot/rockchip/fine3399)：上述三个 Fine3399 文件均存在。Panther 专用文件位于同提交 `panther-x2/`。
- [Fine3399 来源说明](https://github.com/ophub/amlogic-s9xxx-armbian/issues/1790)：该板使用 SW799 系列核心板，OPhub 已有 Fine3399 独立设备支持。
- [OPhub 6.18 Fine3399 DTS](https://github.com/ophub/linux-6.18.y/blob/794930c6844d1fc83990deffcdd787d37df120a0/arch/arm64/boot/dts/rockchip/rk3399-fine3399.dts) 继承 `rk3399.dtsi`；同提交 Makefile 包含两台设备的 DTB 构建项。当前构建固定使用 OPhub `linux-6.18.y` 提交 `a0592d712c819c3571d19ad15ec2d55bd8733a02`（6.18.59），见 `sources.json`。
- [固定内核配置](https://github.com/Lemonade-22/ophub-kernel/blob/35527918391e697f994d9efa02948d4308a7a766/kernel-config/release/stable/config-6.18) 已启用 ARCH_ROCKCHIP、DWMAC_ROCKCHIP、REALTEK_PHY、USB_RTL8152、MMC_DW_ROCKCHIP、MMC_SDHCI_OF_ARASAN、RK808 电源管理和 Rockchip PCIe/NVMe 支持。prepare_kernel.py 保留硬件配置，补 BTF/eBPF/fake-flow、SONiC 和网卡依赖。

因此本方案复用 OPhub 已有板级支持，无需从另一套内核移植 DTS，也不将 Panther DTB 改名给 Fine3399 使用。最终内核包缺少任一所选设备 DTB、缺少所需模块或缺少 SONiC 支持时，打包前直接失败。

## Fine3399 硬件 DTB 与首次启动网络

Fine3399 的硬件描述（GMAC、RGMII 时延、USB、eMMC 等）完全由 OPhub 的官方 `rk3399-fine3399.dtb` 提供，本仓库不修改该 DTB，也没有证据支持改 PHY 地址、时延或替换 DTS。`rk3399-fine3399.dtb` 内现有 RGMII 时延为 `0x28/0x11`；本次不改动。

网络默认值属于 UCI 层，由 `Custom/ARM64-OPhub/fine3399-direct-lan` 写入，仅由 package job 在 `BOARD = fine3399` 时安装到镜像的 `/etc/uci-defaults/99-fine3399-direct-lan`：

- LAN：`eth0`（板载 RTL8211F GMAC）直接使用，不创建单成员 `br-lan` 桥；静态 `192.168.10.1/24`，并显式启用 `dhcp.lan` 服务。实测经过单网口 `br-lan` 时 LAN 入站流量不能正常到达，直接使用 `eth0` 后 DHCP 和后台恢复正常。
- WAN：`eth1`（RTL8153 USB 网卡）DHCP client；`wan6` 使用 `@wan` 的 DHCPv6。WAN/WAN6 在首次启动即写入配置，不检查 `eth1` 是否已枚举；USB 网卡晚出现时由 netifd 自动把接口拉起。
- 脚本只在首次启动运行一次；之后用户可在 LuCI 中自行改桥或端口，不会被持续覆盖。没有 hotplug、开机脚本或轮询检查。
- 该脚本只在 Fine3399 的打包路径安装，不影响 Panther X2。

历史聊天里 LuCI `uci/get` code4 删除 WAN/创建 `br-lan` 的报错没有拿到 RPC trace，本次没有重现，也不声称已修复该独立的 LuCI 问题；本次修复的是首次启动默认网络和构建/内核配套。

## 共用依赖与插件

沿用 Panther 的固定打包器 `028c444dbdb74b1d005affc707cb4cf8adc922a1`，U-Boot、Armbian 启动资源、firmware 和 luci-app-amlogic 的资源锁完整保存在 sources.json。

用户空间固定为 `VIKINGYFY/immortalwrt` 分支 `owrt` 的提交 `de149751183f3c10cff427b7efb1ed5cbcb4b761`。rootfs job 和 kernel job 都从该提交读取：rootfs 直接 clone 该提交，kernel job 用同一提交的 3 个 SONiC 内核补丁。上游 `VIKINGYFY/OpenWRT-CI` 仍按现有逻辑读取 main 并记录实际提交。

内核模板从 `Lemonade-22/ophub-kernel` 的固定提交读取，固定版本的 OPhub 编译工具构建内核、模块和 DTBs，内核版本为 `6.18.59`。配置文件系列从内核版本推导。由于 GitHub Actions 的 `uses` 不能使用动态表达式，编译工具 SHA 同时存在于 workflow 和 sources.json；自动测试核对两者一致。

插件沿用 Panther：每次获取 VIKINGYFY/OpenWRT-CI main 的 GENERAL.txt、Packages.sh、Handles.sh、Settings.sh，主题读取同一快照的 OWRT-ALL.yml；记录上游实际提交。随后应用共用 ARM64 配置，再运行 DAEDE 和 Fakeflow 配置及检查。

上游 `Settings.sh` 会无条件追加 `luci-theme-$WRT_THEME`、`luci-app-$WRT_THEME`、`luci-app-$WRT_THEME-config`。当前主题 `vantage` 只有 `luci-theme-vantage` 和 `luci-app-vantage`，没有 `luci-app-vantage-config`；`make defconfig` 会丢弃未定义的包。`verify_packages.py` 以实际 `tmp/.config-package.in` 为准确认：只有已确认不存在的 `luci-app-vantage-config` 在确实未被任何 feed 定义时才允许跳过；已经定义却被丢弃、以及任何非主题插件被丢弃都仍然失败。不会取消全部包检查。

## SONiC fullcone 的内核/用户空间配套

用户空间包 `fullconenat-sonic` 要求内核带 SONiC 补丁：`CONFIG_NF_NAT_FULLCONE=y`、`CONFIG_NF_CT_PROTO_UDPLITE=y`、`CONFIG_NF_CT_PROTO_SCTP=y`。这些不是可独立加载的 ko，功能位于 `nf_nat` 核心以及 `nft_masq`/`xt_MASQUERADE` 的 `fullcone` 语句/目标中。

本仓库从固定用户空间提交 `de149751183f3c10cff427b7efb1ed5cbcb4b761` 读取并应用 3 个补丁：

- `target/linux/generic/hack-6.18/984-add-sonic-fullcone-support.patch`
- `target/linux/generic/hack-6.18/985-add-sonic-fullcone-to-ipt.patch`
- `target/linux/generic/hack-6.18/986-add-sonic-fullcone-to-nft.patch`

OPhub 6.18.59 的 `nft_masq.c` 已扩展 MASQ 属性，`NFTA_MASQ_MAX` 为 4，而 SONiC 的 `masq_tb` 只有 3 项，且 `nft_fullcone_init()` 原样转发该表。OPhub 的 `nft_masq_init()` 会读取 `tb[NFTA_MASQ_REG_FULLCONE]`（索引 4），越界读取相邻栈内容时可在启动防火墙阶段触发 `nft_masq_init` Oops，并让 fw4 无法建立规则。仓库内 `Custom/ARM64-OPhub/patches/987-fix-ophub-fullcone-attributes.patch` 为 fullcone 建立独立 MASQ 属性表，只复制 FLAGS、REG_PROTO_MIN、REG_PROTO_MAX，避免越界；`prepare_kernel_source.py` 在应用三个 SONiC 补丁后继续应用该兼容补丁，重复准备时会反向检查跳过，并写入 preparation record。测试用 guard page 验证原代码必然触发 SIGSEGV、修复后返回正确错误码且参数完整传递。

kernel job 先把固定 OPhub 内核源码 `a0592d712c819c3571d19ad15ec2d55bd8733a02` 放入 builder 实际复用的 `/mnt/arm64-ophub-kernel/compile-kernel/kernel/linux-6.18.y`，对每个补丁执行 `git apply --check` 后再应用，任何失败立即终止，并输出 patch sha256、diff stat 和 diff sha256 记录。没有使用 builder 的 `kernel_patch` 机制，因为既有编译脚本对 patch 失败只打印 warning，不能作为可靠门禁。

需要报告的构建链限制：`ophub/amlogic-s9xxx-armbian` 的 action 只固定到 `d7ad8779...`；其容器内 `/usr/sbin/armbian-kernel -u` 在每次构建时会从上游 main 更新 `compile-kernel` 脚本。已准备的固定内核源码目录不会被该更新清理，且 `kernel_auto=false` 会复用该源码；但容器内编译脚本本身不是按提交冻结的，这是现有 builder 的锁定边界，不能宣称整条内核构建完全可复现。

`prepare_kernel.py` 在固定 config 上补 SONiC 和网卡关键项：

- SONiC：`NF_NAT_FULLCONE=y`、`NF_CT_PROTO_UDPLITE=y`、`NF_CT_PROTO_SCTP=y`，以及 `NF_NAT`、`NF_NAT_MASQUERADE`、`NF_TABLES`、`NFT_NAT`、`NFT_MASQ`、`NETFILTER_XT_TARGET_MASQUERADE`、`NETFILTER_XT_NAT`。
- Fine3399 网卡/桥接：`STMMAC_ETH`、`STMMAC_PLATFORM`、`DWMAC_ROCKCHIP`、`DWMAC_GENERIC`、`REALTEK_PHY`、`USB_RTL8152`、`BRIDGE`、`BRIDGE_VLAN_FILTERING`、`VLAN_8021Q`，并先核对 `ARCH_ROCKCHIP`、`OF`、`USB`、`USB_SUPPORT`、`PHYLIB`、`MII`、`NETFILTER_ADVANCED`、`NF_CONNTRACK` 等依赖存在。
- OPhub 固定 config 和内核源码本身还带旧的 `CONFIG_NFT_FULLCONE` / `CONFIG_NETFILTER_XT_TARGET_FULLCONENAT`（旧 `nft_fullcone`/`xt_FULLCONENAT` 补丁）。它们与新 SONiC 的 `fullcone` nft 表达式同名，必须不进入最终内核；`prepare_kernel.py` 会移除这些旧符号，`Check-DAEDE-Kernel.py --sonic` 会拒绝旧 config 符号和旧 `*fullcone*.ko`。

内核和打包两个关卡都调用 `Scripts/Check-DAEDE-Kernel.py --sonic`。它检查最终内核 config 的 SONiC 符号、按配置检查 `nf_nat.ko`/`nft_masq.ko`/`xt_MASQUERADE.ko` 是否存在、拒绝旧 fullcone 符号/模块；`--device fine3399` 还检查 STMMAC/DWMAC_ROCKCHIP/REALTEK_PHY/USB_RTL8152 及对应模块。rootfs 关卡额外检查 `CONFIG_PACKAGE_fullconenat-sonic=y`、`firewall4`、`kmod-nft-nat` 和 nftables 默认提供者（`DEFAULT_nftables` 或 `nftables-json`/`nftables-nojson`）已选，且旧 fullcone 包未被选。

## 产物与验证

同次构建先保存 `arm64-ophub-kernel` 和 `arm64-ophub-rootfs`，然后各设备独立下载并校验 SHA256。每台设备的发布文件包含镜像、rootfs、内核请求配置、依赖锁、设备表、插件配置快照、源码和 feeds 提交、引导文件校验值、build-info.txt、SHA256SUMS。

- 本地检查：设备矩阵、固定设备表/引导文件核对、内核 DTB 和模块缺失的拒绝路径、内核包暂存、SONiC gate、固定内核源补丁应用、Actions 语法。
- 云端 `ARM64 OPhub checks`：再次获取固定资源，验证下载接入、用户空间 SONiC 补丁与包元数据、shell/python 语法并运行测试。
- 首次手动构建：确认两份 DTB、镜像、各自引导校验及发布产物，并检查内核产物中的 SONiC 符号和模块。
- Fine3399 实机：确认实际核心板/底板版本和存储容量；验证启动、eth0 LAN/eth1 WAN、DHCP/DHCPv6、USB 晚枚举时 WAN 自动建立、SONiC fullcone 行为、TF/eMMC、USB、所需 PCIe/NVMe、温控及 dae/daed/fake-flow。Wi-Fi、蓝牙和屏幕是否适用及可用按具体硬件测试。

Panther 旧版 `2026.09.17-10.44.03` 有维护者确认可用的历史记录；这不代表新共用 core、SONiC 配套或 Fine3399 已通过实机验证。当前改动交付到移植方案、构建结构与本地可执行验证，不自动触发数小时固件编译，也尚未刷机。

镜像是压缩的整盘 `.img.gz`，应按 OPhub 对应设备安装流程使用，不能当作 OpenWrt 原生 sysupgrade 镜像。默认 LAN 地址为 `192.168.10.1`；账号密码以最终 rootfs/OPhub 设置为准。

## 维护

设备差异改 devices.json；共用 rootfs 选项改 Config/ARM64-OPhub.txt；依赖或固定提交更新改 sources.json 并重跑 ARM64 OPhub checks。涉及内核 builder 更新时同步 workflow 的固定 SHA。若以后设备需要不同内核系列或用户空间，再拆分对应构建组；目前两台均使用同一个 stable 配置。

上游 CI 同步仍由 sync-upstream.yml 处理，共用 Arm64 core 不进入 wrt-core-self.patch。若同步涉及 workflow 文件而默认 GITHUB_TOKEN 无法推送，仓库的 `UPSTREAM_SYNC_TOKEN` 需具有该仓库内容及 workflow 写入权限；同步脚本已有该 Secret 的优先使用逻辑。
