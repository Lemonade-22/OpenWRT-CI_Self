# Q6000 eMMC → VIKINGYFY OWRT

## 适配依据

主要来源是 [dailook/immortalwrt-24.10 的 Q6000 eMMC 适配](https://github.com/dailook/immortalwrt-24.10/blob/openwrt-24.10/target/linux/mediatek/dts/mt7986a-ikuai-q6000-emmc.dts)，并对照用户提供的同名 DTS。两者硬件配置一致，型号显示文本不同。
chenhans233 的 110M NAND/闭源无线适配不是本次移植基线。

目标源码：[VIKINGYFY/immortalwrt owrt](https://github.com/VIKINGYFY/immortalwrt/tree/owrt)，本次核对提交 4e21fd0651eed0efaea4cc5a3ff73c2f07b1e2a2，Linux 6.18 系列。专用 CI 每次克隆 owrt 分支，再检查并应用补丁；源码更新导致补丁不适用时停止。

## RE-CP-03 能参考什么

dailook 的 Q6000 eMMC 和 RE-CP-03 同为 sysupgrade-tar 和 emmc_do_upgrade 路线。
但是 OWRT 当前的 RE-CP-03 已采用 production 分区、root=/dev/fit0 和 sysupgrade.itb：
[设备树](https://github.com/VIKINGYFY/immortalwrt/blob/owrt/target/linux/mediatek/dts/mt7986a-jdcloud-re-cp-03.dts)、
[镜像定义](https://github.com/VIKINGYFY/immortalwrt/blob/owrt/target/linux/mediatek/image/filogic.mk)。

2026-09-18 的 [OWRT 发布](https://github.com/VIKINGYFY/OpenWRT-CI/releases/tag/MEDIATEK-WIFI-YES-VIKINGYFY-owrt-26.09.18-07.39.36)包含 RE-CP-03 的 sysupgrade.itb、GPT、preloader 和 FIP；发布标注源码提交与上述目标提交一致、内核 6.18.44。本次核对发布元数据及对应源码，未解包二进制固件。

| 项目 | Q6000 eMMC | OWRT RE-CP-03 |
|---|---|---|
| DTS 内存声明 | 512MiB | 1GiB |
| 外置 WAN PHY 地址 | 3 | 6 |
| LAN 交换机端口 | 4/3/2 → lan1/lan2/lan3 | 1/2/3/4 → lan1/lan2/lan3/lan4 |
| Reset / 第二按键 GPIO | 7 / 15 | 9 / 10 |
| EEPROM | factory + 0，长度 0x1000 | 同左 |
| LAN / WAN MAC 偏移 | 0x4 / 0x10048 | 0x2a / 0x24 |
| 根文件系统 | PARTLABEL=rootfs | fit0，production 分区 |
| 升级镜像 | sysupgrade.bin（tar） | sysupgrade.itb |

因此只借鉴 MT7986、eMMC 引脚的新内核写法、mt76 和 NVMEM 驱动方案；保持 Q6000 上游硬件参数及 kernel/rootfs 布局。不复制 RE-CP-03 的 GPT、引导程序或固件。

## 已加入的适配

- 新增 ikuai_q6000-emmc profile 和设备树。
- 保留原始 MAC/EEPROM 偏移、GPIO、网口和 eMMC 时序；转换旧式 pull-up/down 属性为当前 MTK pinctrl 写法，纠正节点地址名称。
- LAN 为 lan1 lan2 lan3，WAN 为 eth1。
- 使用 mt7915e/MT7986 固件与 WO 固件；不引入 mt_wifi。
- sysupgrade.bin 使用上游的 tar 结构；升级与配置保存接入当前 emmc_do_upgrade / emmc_copy_config。
- 专用 Q6000-EMMC 手动工作流应用补丁；普通 MTK 和其他设备构建不变。
- 在 GENERAL 和自定义设置合并后启用 initramfs，提供 RAM 测试镜像。

## 构建与使用范围

合并后在 Actions 选择 Q6000-EMMC，TEST=false 编译；TEST=true 只展开配置，不编译固件。
沿用仓库默认插件、主题与网络设置。
产物包括 Q6000 的 sysupgrade.bin 和 initramfs 镜像，以编译结果为准。
sysupgrade.bin 不是裸 eMMC 全盘镜像；能否从 U-Boot 网页直接接收取决于该 U-Boot 是否支持这种 tar 固件。
不生成通用 GPT、BL2、FIP 或带猜测偏移的 factory 镜像。

前提是现有 Q6000 eMMC 引导布局具有 factory、kernel、rootfs 分区，且 kernel/rootfs 容量足够。
这份 DTS 不提供分区起始扇区与容量，无法由它推导全盘刷入镜像。
本适配不会主动修改分区表、引导程序或校准数据。

## 验证

已完成补丁应用检查、变更文件检查、工作流 YAML 与 shell 静态检查。
尚未完成完整固件编译、DTB 编译/schema 校验或实机测试。
需要实机验证冷启动、eMMC 稳定性、WAN 协商、LAN 顺序、MAC、双频无线和 WED/硬件加速。
