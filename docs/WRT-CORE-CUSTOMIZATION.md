# WRT-CORE 上游同步与本地定制

`.github/workflows/WRT-CORE.yml` 保持上游原版。本地修改集中在
`patches/wrt-core-self.patch`，由 `Scripts/Generate-Wrt-Core.py` 应用到临时副本，
生成统一的 `.github/workflows/WRT-CORE-SELF.yml`。

AP8220、ZN-M2、MT7621、MTK-ALL、OWRT-ALL、QCA-ALL、QCB-ALL、AIROHA-ALL 和 WRT-TEST
都调用这一份定制核心。N60 Pro 也走这一份（见“N60 Pro 512M”一节）；只有 Airoha NWRT/原生
和 ARM64 OPhub 用自己的专用构建路径。

ARM32 兼容层见 [内核兼容支持](KERNEL-COMPAT.md)：只有选了 `zte-mesh` 的构建才会启用
`CONFIG_COMPAT` 和原厂运行环境需要的 SysV IPC、命名空间，未选该包的固件整体跳过、`.config` 不动。

通用补丁保留 APT 换源参数、NSS 选项检查、DAEDE 配置和验证，以及
固件信息去重。环境依赖安装采用当前上游的 `apt-get` 和显式依赖列表。

## 上游脚本的同步策略

`Settings.sh` 不再保存副本。构建时由 `Scripts/Settings.sh` 从
`VIKINGYFY/OpenWRT-CI@main` 现拉上游原文并原样执行，本仓库的加分项放在
`Scripts/Settings-Extra.sh`，只追加、不改写。

之所以这样拆：旧做法是手工复制一份（本地 106 行 vs 上游 53 行）。副本无法跟随上游，
上游在 10 月 27 日和 31 日两次改动都进不来；更糟的是副本里把 `luci-app-<theme>` 那行
换成了 `-config` 的条件判断，于是所有机型都只装主题、不装仪表盘（vantage 的落地页），
而且不报错。

`Settings-Extra.sh` 里只剩三件上游不负责的事，全是追加：

1. 机型覆盖配置 `Config/<CONFIG>-EXTRA.txt`
2. ramips 6.18 的 RTL837x DSA 补丁程序
3. LuCI 默认主题（含旧配置回落到所选主题的 uci-defaults）

**WIFI 账号密码归上游**：本树 `mac80211.uc` 的回退值就是 `OWRT` / `12345678`，与各流程传入的
`WRT_SSID` / `WRT_WORD` 一致，本地再补一段 sed 属于重复劳动，还会跟上游将来的写法打架，已删除。

**没有任何机型被特殊对待。** 旧版本曾让 `ZN-M2-WIFI-NO` 跳过上游的 DTS 改写（保留原厂
qualcommax 布局），现已删除：上游在 `WIFI-NO` 时把 `#include "ipq6018.dtsi"` 换成
`ipq6018-nowifi.dtsi`，重排 `q6_region` 等分区，ZN-M2（IPQ6000，`qualcommax` 的 `ipq60xx`
子目标）也照此执行。若这一机型因此出问题，那是上游策略或设备本来的限制，不再在本仓库里分叉。

上游哪天改了 `Settings.sh`，直接生效。本仓库不再依赖它的任何内部变量或行文，所以上游重构
不会把某个定制悄悄甩下——最多是 `Settings-Extra.sh` 里那三件追加的事需要重新确认。

`Handles.sh` 和 `Packages.sh` 目前仍是本地副本（分别比上游多 7 行和 22 行），同一个毛病
还没修，改动时会再核对。

## daed：只准备内核，不预装任何东西

`Scripts/DAEDE.sh` 现在只做一件事：把 `Config/DAEDE.txt` 里的 eBPF 内核前置依赖写进 `.config`，
（BTF、cgroup BPF、kprobes、`kmod-sched-bpf`、`kmod-nft-tproxy`、`ca-bundle`、`curl` 等）。

**镜像里不带 `daed`、`dae`、`luci-app-daede`，也不带 `geoip.dat` / `geosite.dat`。** 需要时由使用者
自己 `apk add`，装完即可用，因为内核前置已经就位。

为什么不做预装：

- 用 `files/` 覆盖安装的包不会写进 apk 的已安装数据库，daede 面板会显示「非包管理器安装 /
  未安装」，更新按钮也是灰的——半残的面板比没有更迷惑人。
- geo 两份数据约 10 MiB，在小型 NAND 机型上直接吃掉可写 overlay 的空间。

`verify` 只拦一件事：`files/` 里又冒出 `usr/bin/daed` 或 `usr/share/v2ray/geoip.dat`。
daed 相关包不再被强制置为 not set——装不装由使用者决定。

## 全设备静态地址绑定

通用定制核心、N60 Pro、Airoha NWRT/原生和 ARM64 OPhub 都调用
`Scripts/Static-Gateway.sh`，从 `Lemonade-22/luci-app-static-gw` 的 main
分支拉取插件并记录提交号。脚本在设备配置和手动包选项之后将插件设为内置，
在 `make defconfig` 后确认仍然选中，避免构建出缺少插件的固件。

## 所有定制核心机型及 N60 Pro 的 Mesh 支持

`Scripts/Mesh.sh prepare` 在软件包处理完成后拉取
`xxosdev/luci-app-mesh` 的 main 分支，并在构建日志记录提交号。
插件的 wpad 依赖改为同样支持 802.11s/SAE 的完整版 `wpad-openssl`，
保留完整认证功能；batctl 使用 `batctl-full`，包含状态查询与诊断命令。

`Config/MESH.txt` 为所有调用 WRT-CORE-SELF 的配置启用插件、LuCI batman
协议、dawn/umdns、mac80211 802.11s、batman-adv、加密模块和 CRC16，
以及 BATMAN V、BLA、DAT、MCAST。其余传递依赖由当前源码的包依赖自动选择，
例如适用内核版本的 CRC32C。无需强开仅供开发调试的 tracing/debug。

`configure` 在私有配置、机型覆盖和手动包选项之后执行，统一移除冲突的
wpad/hostapd/supplicant 提供者；`verify` 在 `make defconfig` 后核对每项依赖。
缺包、被目标限制移除或重新选中冲突提供者时终止构建，避免输出缺依赖的固件。

WIFI-NO、X86 和测试配置同样包含这些包，但不会修改 DTS、恢复被禁用的无线
设备或自动启用组网。实际无线 Mesh 仍需要可工作的无线设备及支持 mesh point
的驱动。N60 Pro 也走同一套 prepare/configure/verify 流程，
在现有 eBPF（DAEDE）配置之后应用 Mesh 配置，在配置哈希计算前完成验证。
使用独立核心的 XG-040G 和 Panther-X2 不在此次修改范围内。

本次本地验证覆盖脚本语法、配置替换/缺依赖检测及工作流生成测试；完整固件编译、
各设备镜像大小和实机无线组网仍需对应 GitHub Actions 构建及设备验证。

## Wi-Fi 双版本

ZN-M2、AP8220（单分区）和 N60 Pro 各出两版。手动触发时用一个 `WIFI` 下拉（`YES` / `NO`）选择，
和 `固件类型` 那个下拉一样，不会在 Actions 里堆出两份工作流。配置名后缀决定行为：

| 机型 | WIFI-YES | WIFI-NO |
| --- | --- | --- |
| ZN-M2 | `ZN-M2-WIFI-YES` | `ZN-M2-WIFI-NO` |
| AP8220 1G 单分区 | `IPQ807X-AP8220-1G-SINGLE-WIFI-YES` | `IPQ807X-AP8220-1G-SINGLE-WIFI-NO` |
| N60 Pro 512M | `N60-Pro-512M-WIFI-YES` | `N60-Pro-512M-WIFI-NO` |

`WRT_WIFI` 由配置名后缀推导（`WIFI-(YES|NO)$`）。`Scripts/Mesh.sh` 在 `WIFI-NO` 时直接退出，
不克隆 `luci-app-mesh`、不写入 `Config/MESH.txt`，所以无 Wi-Fi 固件里没有 wpad/batman/dawn。

关无线的两种写法，各按对应平台的上游做法来：

- **qualcommax（ZN-M2、AP8220）**：`CONFIG_PACKAGE_kmod-ath=n` 等逐个关闭，与上游
  `IPQ60XX-WIFI-NO.txt` / `IPQ807X-WIFI-NO.txt` 一致。WIFI-YES 版删掉这些关闭行，无线包由
  target `DEFAULT_PACKAGES` 与设备固件带入。
- **mediatek（N60 Pro）**：上游没有 N60 Pro 的无 Wi-Fi 版，参照 `MEDIATEK-WIFI-NO.txt` 里
  `supergateway_s20p` 的做法按设备剥包：
  `CONFIG_TARGET_DEVICE_PACKAGES_mediatek_filogic_DEVICE_netcore_n60-pro="-kmod-mt76 -kmod-mt7915e ... -mt7986-wo-firmware"`，
  保留 `kmod-usb3`、`automount`。

AP8220 单分区的分区与产物逻辑在 `Scripts/Device-Hooks/IPQ807X-AP8220-1G-SINGLE-WIFI-NO.sh`，
WIFI-YES 用薄壳钩子转发过去，两个版本不会分叉。


## N60 Pro 512M

Netcore N60 Pro 有 512 MB NAND，但设备树把 ubi 分区写死在 122.5 MiB（`0x7a80000`），固件因此
只认这么点空间。`patches/n60pro-512m-ubi-5065m.patch` 把该分区改成 `0x1fa80000`（约 506.5 MiB），
由 `Scripts/Device-Hooks/N60-Pro-512M-WIFI-{YES,NO}.sh` 在 `prepare` 阶段应用，`verify` 与
`verify-image` 阶段分别核对分区没被打回、产物不超过整片 NAND。

除此之外没有专用逻辑：主题、Mesh、DAEDE、静态地址、内核兼容、缓存和发布全部由
`WRT-CORE-SELF.yml` 提供。早先那份 321 行的独立工作流把通用核心的步骤抄了一份，
既容易漂移，也让每次改动要改两处，已删除。

## 设备专用脚本

设备专用逻辑按配置名放在 `Scripts/Device-Hooks/<WRT_CONFIG>.sh`。通用核心在既有
准备、配置、校验、打包阶段调用 `Scripts/Device.sh`；不存在对应钩子时直接返回成功。
因此其他设备的步骤名称与日志中不会出现 AP8220 专用确认，而 AP8220 运行时会在
对应通用步骤内执行自己的检查。

目前 `IPQ807X-AP8220-1G-WIFI-NO.sh` 负责 1 GiB NAND 适配、配置和镜像校验、
安装指南、校验和及发布正文。通用上传和发布步骤只使用设备脚本设置的产物名称。

## 同步上游

`sync-upstream.yml` 合并上游后，自动重新生成并提交定制版，再推送到 `main`。
上游修改未涉及补丁上下文时会正常带入定制版；若补丁无法应用，则在推送前报错，
需要调整补丁后再运行同步。其他文件发生 Git 合并冲突时仍需单独解决。

生成的工作流必须提交：GitHub Actions 从调用方所在的提交读取可复用工作流，
不能在构建任务运行中修改 YAML 来改变已经解析的步骤。

## 修改定制内容

通用构建行为修改 `patches/wrt-core-self.patch`；单设备行为修改对应
`Scripts/Device-Hooks/*.sh`。然后运行：

```sh
python3 Scripts/Generate-Wrt-Core.py
python3 Scripts/Generate-Wrt-Core.py --check
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

将补丁、设备脚本和生成的 `WRT-CORE-SELF.yml` 一起提交。不要直接修改
`WRT-CORE.yml`，也不要只提交对生成文件的手工修改；一致性检查会检测未重新生成的工作流。

需要较大调整时，可以先在独立临时目录中修改上游文件的副本，再使用 `git diff`
重新制作补丁。补丁的文件头应为 `a/.github/workflows/WRT-CORE.yml` 和
`b/.github/workflows/WRT-CORE.yml`。