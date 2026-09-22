# NN6000 v2 / ZN M2

在 Actions 中选择 **IPQ60XX-NN6000V2-ZN-M2**，点击 Run workflow。

- 源码：`VIKINGYFY/immortalwrt` 的 `owrt` 分支。
- 平台：`qualcommax/ipq60xx`，一次编译两款设备，各自生成固件。
- 仅选择 `link_nn6000-v2` 和 `zn_m2`，保留设备默认无线驱动和固件。
- 默认地址 `192.168.10.1`，主机名和 Wi-Fi 名称 `OWRT`，Wi-Fi 密码 `12345678`。
- 沿用 MT7621 的 aurora 主题、通用插件配置和三个插件排除项。
- PACKAGE 可以追加插件配置；TEST 勾选后仅生成配置，不编译固件。

## DAEDE 依赖

通过公共 `WRT-CORE.yml` 调用 `Scripts/DAEDE.sh`，在通用配置、设备覆盖和手动插件配置之后应用 `Config/DAEDE.txt`：

- 内核调试信息与 BTF，关闭 DEBUG_INFO_REDUCED。
- cgroups / cgroup BPF、kprobes / kprobe events、BPF events、BPF stream parser。
- XDP sockets；源码支持时启用 NETKIT。
- kmod-sched-core、kmod-sched-bpf、kmod-veth、kmod-xdp-sockets-diag。
- ca-bundle、curl、ip-full，并关闭 ip-tiny。

`make defconfig` 后校验必需配置；缺失时工作流失败，防止配置被依赖规则静默关闭。
遵循现有公共配置，只准备 dae/daed/DAEDE 的依赖，不预装这些程序或 LuCI 插件。
新增配置已按源码设备定义和公共依赖处理流程核对；实际固件编译、镜像大小与设备运行仍需通过构建和实机验证。

固件发布在 Releases；请按文件名中的 `link_nn6000-v2` 或 `zn_m2` 选择对应设备。
