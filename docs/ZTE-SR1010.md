# ZTE SR1010 OWRT

入口：Actions → **ZTE SR1010 OWRT** → Run workflow。

- 固件源码：`Lemonade-22/immortalwrt` 的 `sr1010-zx279133` 分支。
- 本次同步基线：`cnjn/immortalwrt@ac68c3f8ecb2924c3b763a955e8c9820713c1e7e`。
- 平台：`zte/zx279133`，设备：`zte_zxslc-sr1010`，内核来自该分支的 Linux 7.3 补丁系列。
- 默认地址 `192.168.10.1`，主机名 `OWRT`，初始 root 密码为空；不提供无线驱动。
- Footstrap 主题；继承 `Config/GENERAL.txt` 和 MT7621 workflow 的包覆盖项。预装自动重启、磁盘管理、NATMapT、分区扩容、UPnP；排除 MT7621 所排除的 HomeProxy、GecoosAC、WolUltra、Samba4 和 Aurora。
- 保留 SR1010 的 NPU、硬件转发、交换机、CPU 频率与固件槽位管理。
- 保留上游固定的 LuCI feed，只单独引入与 MT7621 同源的 Footstrap；外部软件的实际提交记录在 `sources.txt`。

`TEST=true` 只生成并验证配置，保存配置 Artifact。默认 `TEST=false` 编译完整固件；`RELEASE=true` 在成功保存固件 Artifact 后发布 Release。`PACKAGE` 每行接受 `CONFIG_PACKAGE_包名=y/m/n`，设备必需项和默认主题不能被取消。

主镜像：`immortalwrt-zte-zx279133-zte_zxslc-sr1010-squashfs-sysupgrade.bin`。同时保存最终配置、diffconfig、源码版本、包清单和 SHA256。上游打包器检查固件槽位容量，workflow 另外检查主镜像存在且非空。

镜像使用上游 SR1010 专用格式，包含修补过的 U-Boot。创建 workflow 或通过配置检查不代表已编译，也不代表已验证实机启动。刷写前按上游 SR1010 文档核对设备与恢复方式。
