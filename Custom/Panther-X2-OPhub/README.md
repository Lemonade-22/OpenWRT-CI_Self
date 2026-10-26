# Panther X2 已归入共用 ARM64 方案

完整方案、固定来源、产物格式和验证要求见 [ARM64 OPhub 文档](../ARM64-OPhub/README.md)。

构建入口：Actions → ARM64-ALL → device 选择 `panther-x2`。原 Panther-X2-OPhub-OWRT 单独 workflow 已删除。

共用脚本和 sources.json 已移到 `Custom/ARM64-OPhub/`，rootfs 配置移到 `Config/ARM64-OPhub.txt`。设备特有的 DTB、引导组合、分区容量和 Release 前缀在 `Custom/ARM64-OPhub/devices.json` 中维护。

Panther 仍采用 RK3566 专用 `rk3566-panther-x2.dtb`、`idbloader.img` 和 `u-boot.itb`，保留 `Panther-X2-OPhub-OWRT` Release 前缀。历史版本 2026.09.17-10.44.03 的可用记录保留；新的共用构建结构需独立完成构建与实机验证。
