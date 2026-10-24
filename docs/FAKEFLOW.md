# fake-flow 运行依赖

以下构建通过 `Scripts/Fakeflow.sh` 在用户配置之后、`make defconfig` 之前应用
`Config/FAKEFLOW.txt`，并在配置展开后检查所有依赖仍为内置软件包：

| Actions 工作流 | 配置 / 接入位置 |
| --- | --- |
| AP8220-1G（PPE / NSS） | IPQ807X-AP8220-1G-WIFI-NO / AP8220-CORE |
| ZN-M2-WIFI-NO（PPE / NSS） | ZN-M2-WIFI-NO / WRT-CORE-SELF |
| N60 Pro 512M UBI-506M | N60-Pro-512M / n60-pro-512m-core |
| XG-040G-MD-NATIVE | AIROHA-MD-NATIVE / air-native-core |
| XG-040G-MD-NWRT | AIROHA-NWRT / air-core |
| Panther-X2-OPhub-OWRT | Panther-X2-OPhub / 独立 rootfs 和内核构建 |

依赖包含 libbpf、libelf、zlib、ip-full、tc-full、kmod-sched-core、
kmod-sched-bpf、kmod-dummy、kmod-tun。对应 TC/clsact、BPF classifier/action、
dummy 和 L3 TUN 模式。现有 BTF/eBPF 配置继续保留；其他设备不应用此依赖清单。
AP8220 adaptation checks 是适配检查流程，不生成固件；它检查新增脚本的语法。

Panther X2 打包会替换 rootfs 的内核模块，因此 `prepare_kernel.py` 还为最终
ophub 内核启用 DUMMY/TUN。内核构建后和打包前，`Check-DAEDE-Kernel.py --fakeflow`
检查实际内核配置；若选为模块，则要求归档内包含 dummy.ko / tun.ko，允许压缩模块。
既有 BPF、TC 和设备树检查继续执行。

本次只预置运行依赖，不内置 fake-flow 主程序，不自动启动服务，也不改变现有
NSS/PPE/NPU 加速设置。安装匹配固件架构及库 ABI 的 fake-flow 后，仍需实机检查
加载结果及 WAN 流量是否经过 TC 挂点；构建配置通过不等于硬件加速共存已经验证。

需求依据：https://github.com/Lemonade-22/fake-flow 的 README 和 packaging/openwrt/Makefile。
