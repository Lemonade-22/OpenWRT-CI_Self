# WRT-CORE 上游同步与本地定制

`.github/workflows/WRT-CORE.yml` 保持上游原版。本地修改集中在
`patches/wrt-core-self.patch`，由 `Scripts/Generate-Wrt-Core.py` 应用到临时副本，
生成统一的 `.github/workflows/WRT-CORE-SELF.yml`。

AP8220、ZN-M2、MT7621、MTK-ALL、OWRT-ALL、QCA-ALL、QCB-ALL、AIROHA-ALL 和 WRT-TEST
都调用这一份定制核心。N60 Pro、Airoha NWRT/原生、ARM64 OPhub 使用各自的专用构建路径。

ARM32 兼容层见 [内核兼容支持](KERNEL-COMPAT.md)：只有选了 `zte-mesh` 的构建才会启用
`CONFIG_COMPAT` 和原厂运行环境需要的 SysV IPC、命名空间，未选该包的固件整体跳过、`.config` 不动。

通用补丁保留 APT 换源参数、NSS 选项检查、DAEDE 配置和验证，以及
固件信息去重。环境依赖安装采用当前上游的 `apt-get` 和显式依赖列表。

## daed 代理后端

除 MT7621 外的所有构建入口都调用 `Scripts/DAEDE.sh`：拉取
[openwrt-daede](https://github.com/kenzok8/openwrt-daede) 到 `package/openwrt-daede`，
选中 `daed` 与 `luci-app-daede`，**不选 `dae`**（daed 已内嵌同一内核，界面也共用一套 UCI）。
`v2ray-geoip`/`v2ray-geosite` 由 `daed` 的依赖带入，设备上再由 `geo-cron.sh` 更新。
`dae/` 目录必须留在树里：`luci-app-daede` 的 install 读取 `../dae/files/dae.config`。

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
的驱动。N60 Pro 的独立核心也调用同一套 prepare/configure/verify 流程，
在现有 eBPF（DAEDE）配置之后应用 Mesh 配置，在配置哈希计算前完成验证。
使用独立核心的 XG-040G 和 Panther-X2 不在此次修改范围内。

本次本地验证覆盖脚本语法、配置替换/缺依赖检测及工作流生成测试；完整固件编译、
各设备镜像大小和实机无线组网仍需对应 GitHub Actions 构建及设备验证。

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
