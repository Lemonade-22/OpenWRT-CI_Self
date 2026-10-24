# WRT-CORE 上游同步与本地定制

`.github/workflows/WRT-CORE.yml` 保持上游原版。本地修改集中在
`patches/wrt-core-self.patch`，由 `Scripts/Generate-Wrt-Core.py` 应用到临时副本，
生成统一的 `.github/workflows/WRT-CORE-SELF.yml`。

AP8220、ZN-M2、MT7621、MTK-ALL、OWRT-ALL、QCA-ALL、QCB-ALL 和 WRT-TEST
都调用这一份定制核心。Airoha、N60 Pro、Panther-X2 的独立构建方式不变。

通用补丁保留 APT 换源参数、NSS 选项检查、DAEDE/Fakeflow 配置和验证，以及
固件信息去重。环境依赖安装采用当前上游的 `apt-get` 和显式依赖列表。

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
