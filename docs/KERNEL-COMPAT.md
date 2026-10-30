# ARM64 上执行 ARM32 程序

所有固件构建入口通过 `Scripts/kernel_compat.py` 共用以下要求：

- ARM64：`CONFIG_COMPAT=y`，为支持 AArch32 的 CPU 提供 ARM32 用户态兼容。
- 明确启用 `KUSER_HELPERS`、`COMPAT_ALIGNMENT_FIXUPS`，避免 COMPAT 打开后 Linux
  `syncconfig` 遇到新选项向 CI 提问并退出；较老内核没有的 alignment fixups 符号由 Kconfig 丢弃。
- 所有架构：`SYSVIPC`、`NAMESPACES`、`IPC_NS`、`NET_NS`、`PACKET`、`TMPFS`、`BINFMT_ELF` 内建启用。

OpenWrt 配置在设备与私有设置之后、`make defconfig` 之前应用，随后检查是否保留。部分源码没有
`KERNEL_COMPAT`、`KERNEL_SYSVIPC` 等菜单符号，脚本会补充隐藏的 Kconfig 入口，让
`CONFIG_KERNEL_*` 经 OpenWrt 的 `include/kernel-defaults.mk` 传递到 Linux，而不是只向 `.config`
追加一行随后被 defconfig 丢弃。

普通 OpenWrt、N60 专用、Airoha NWRT/原生构建均在编译完成后检查真正的 Linux `.config`，缺项则停止发布。
OPhub 路径另外修改最终外部内核配置，并通过现有内核归档校验检查实际产物；只修改其 rootfs 配置不足以改变外部内核。
通用 core 的改动保存在 `patches/wrt-core-self.patch`，并同步生成 `WRT-CORE-SELF.yml`，保留上游 core 原文件。

32 位目标无需 ARM64 的 COMPAT；x86 等架构不能借此运行 ARM32 原厂程序。即使内核启用 COMPAT，CPU 也必须
支持 AArch32。此改动不会把闭源 ARM32 程序转换成 ARM64，也不会修改现有已发布固件；设备需要重新构建和升级。

zte-mesh 的 `ip-full`、`kmod-veth`、`kmod-sched-core` 是软件包依赖，仍须随设备固件或配套软件源提供。
