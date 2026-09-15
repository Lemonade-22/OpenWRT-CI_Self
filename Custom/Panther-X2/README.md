# Panther X2 原生 ImmortalWrt 构建

本目录在 CI 拉取 VIKINGYFY/immortalwrt 的 owrt 最新源码后应用设备适配，无需维护另一个源码仓库。

## 构建

在 Actions 中打开 **Panther-X2-Native**，选择 Run workflow。TEST=true 仅生成配置；TEST=false 编译并发布固件。配置检查通过只表示设备和 U-Boot 被选中，不代表内核或 U-Boot 已编译，更不代表实机启动成功。

独立配置为 `Config/Panther-X2-OWRT.txt`，默认地址沿用 192.168.10.1，内核分区 128 MiB，根分区 1024 MiB。保留原有有线设备配置，不额外添加无线软件包；这不表示所有 Panther X2 硬件都没有无线芯片。

如需在 ROCKCHIP 批量构建中加入本设备，可在 `Config/ROCKCHIP.txt` 添加 `CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_panther_x2=y`。Settings.sh 根据设备选项应用适配，WRT-CORE 在 make defconfig 后检查选项是否被丢弃。

## 来源与修改

Linux DTS 和 U-Boot defconfig 补丁来自 coolsnowwolf/lede 提交 `611233e63e3e0aefbb6fbac67252e9c44791a7a9`，原始路径保存在 files/ 中，保留原有许可证和作者署名。DTS 的 SPDX 为 GPL-2.0+ OR MIT；U-Boot 补丁遵循上游 U-Boot/LEDE 的适用许可证。

integration.patch 添加 Panther X2 Device、U-Boot 定义与构建目标。设备继承 VIKINGYFY 的 Device/rk3566，使用其默认 FIT 内核与 pine64-img 镜像流程；DDR/ATF 仍由目标树的 RK3566 引导依赖提供。专用 bootscript 显式设置 RK3566 UART2 和 PARTUUID 根分区启动参数。

apply.py 校验 sources.json 中的 SHA256，在改动前检查补丁与已有文件冲突，支持同一适配的重复调用。发生冲突时退出失败，不静默覆盖未来上游新增的支持。构建产物附带 Panther-X2-sources.json，记录 LEDE 提交、素材哈希和实际 ImmortalWrt 提交。

## 上游同步

现有 sync-upstream.yml 每小时第 17 分钟检查 VIKINGYFY/OpenWRT-CI/main，也可手动运行。GitHub 调度可能延迟，不是实时事件同步。使用正常 merge 保留定制，冲突时失败并列出文件；不强制覆盖。每次固件构建仍直接拉取最新 owrt 分支。

默认使用 GITHUB_TOKEN。若同步涉及工作流文件而被 GitHub 拒绝，可设置仅授权此仓库的 `UPSTREAM_SYNC_TOKEN` secret：fine-grained PAT 需要 Contents 和 Workflows 写权限；经典 PAT 需要适当仓库权限及 workflow scope。分支保护也可能要求人工合并。不要把令牌写进文件或日志。没有新令牌时普通同步仍按现有方式尝试，失败在 Actions 中明确报告。

更新 LEDE 适配时应选择固定提交，检查与当前 ImmortalWrt 内核/U-Boot 的兼容性，再更新素材和 sources.json 哈希。不要自动替换整个 Rockchip 或 package/boot 目录。

## 验证范围

运行 `python3 Custom/Panther-X2/test_apply.py /path/to/clean/immortalwrt` 可验证首次应用、重复应用、冲突时不改文件和配置丢失检测。完整编译需要 Linux 构建环境或 GitHub Actions。

首次固件必须通过可恢复启动介质及串口验证：DDR/U-Boot、内核挂载、eth0、MAC 地址稳定性、eMMC/SD、USB和重启。网口沿用目标树默认单网口 eth0 LAN 规则。尚未实机验证前，不应把镜像视为已验证的 eMMC 升级包，尤其不要直接从 ophub 布局保留配置升级。
