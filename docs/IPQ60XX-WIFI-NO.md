# NN6000 v2 / ZN M2 无 Wi-Fi 固件

在 Actions 选择 **IPQ60XX-WIFI-NO**，点击 Run workflow。旧的
`IPQ60XX-NN6000V2-ZN-M2` 工作流已删除，不要重新运行旧任务。

- 参考 VIKINGYFY/OpenWRT-CI 的 `IPQ60XX-WIFI-NO.txt` 和 `Settings.sh`，
  只构建 `link_nn6000-v2`、`zn_m2`，分别生成固件。
- 源码仍为 `VIKINGYFY/immortalwrt` 的 `owrt` 分支，内核跟随该分支
  （本次核对为 6.18）。LEDE 仓库的 6.12 工作流不受影响。
- 使用上游 `ipq6018-nowifi.dtsi` 的内存配置；移除无线驱动、固件、
  板级无线数据和 wpad 的默认选择，防止 per-device rootfs 把它们选回来。
- 软件沿用 MT7621 的 `GENERAL.txt` 和应用排除项：不包含 gecoosac、
  homeproxy、wolultra。保留其余通用应用；硬件驱动按 IPQ60xx 配置。
- 默认主题为 ImmortalWrt LuCI 上游的 `luci-theme-footstrap`。
  每次更新 feeds 时获取最新代码，不引入 Aurora 主题或设置插件。
  Footstrap 与 Aurora 共用的 `luci-base` 是 LuCI 必需组件，继续保留。
- 默认管理地址 `192.168.10.1`，主机名 `OWRT`，无默认密码。
- PACKAGE 可追加配置；TEST 只生成并校验配置，不编译固件。

## dae / daed 内核与模块依赖

按 [kenzok8/openwrt-daede](https://github.com/kenzok8/openwrt-daede) 的要求，
通过公共 `Config/DAEDE.txt` 开启 BTF、cgroup BPF、kprobes、BPF events、
BPF stream parser、XDP sockets、调度 BPF、veth、XDP 诊断、nftables TPROXY；
保留 ca-bundle、curl 和 ip-full。源码提供 NETKIT 时也开启。

只准备运行依赖，不预装 dae、daed 或 luci-app-daede。
安装 luci-app-daede 时仍需安装与它配套的 dae/daed 后端软件包；
开启内核依赖不能替代用户空间软件包。

构建前校验配置，构建后检查实际 Linux `.config`、模块和两款设备的
软件包清单。NN6000 v2 使用 LZMA FIT，并检查 sysupgrade 中的内核不超过
原有 6 MiB 分区。固件仍需通过完整编译和实机验证。
