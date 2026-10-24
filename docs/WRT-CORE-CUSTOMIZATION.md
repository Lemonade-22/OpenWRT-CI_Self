# WRT-CORE 上游同步与本地定制

`.github/workflows/WRT-CORE.yml` 保持上游原版。定制修改集中在
`patches/wrt-core-self.patch`，由 `Scripts/Generate-Wrt-Core.py` 应用到临时副本，
生成 `.github/workflows/WRT-CORE-SELF.yml`，不会修改上游原文件。

现有 AP8220、ZN-M2、MT7621、MTK-ALL、OWRT-ALL、QCA-ALL、QCB-ALL 和
WRT-TEST 入口调用定制版。Airoha、N60 Pro、Panther-X2 的独立构建方式不变。

补丁保留 APT 换源参数、AP8220 1 GiB NAND 适配及镜像检查、NSS 选项检查、
DAEDE/Fakeflow 配置和验证、固件信息去重，以及 AP8220 独立打包与发布逻辑。
环境依赖安装采用当前上游的 `apt-get` 和显式依赖列表。

## 同步上游

`sync-upstream.yml` 合并上游后，自动重新生成并提交定制版，再推送到 `main`。
上游修改未涉及补丁上下文时会正常带入定制版；若补丁无法应用，则在推送前报错，
需要调整补丁后再运行同步。其他文件发生 Git 合并冲突时仍需单独解决。

生成的工作流必须提交：GitHub Actions 从调用方所在的提交读取可复用工作流，
不能在构建任务运行中修改 YAML 来改变已经解析的步骤。

## 修改定制内容

编辑 `patches/wrt-core-self.patch`，然后运行：

```sh
python3 Scripts/Generate-Wrt-Core.py
python3 Scripts/Generate-Wrt-Core.py --check
python3 -m unittest discover -s tests -p test_wrt_core_generation.py -v
```

将补丁和生成的 `WRT-CORE-SELF.yml` 一起提交。不要直接修改 `WRT-CORE.yml`，
也不要只提交对生成文件的手工修改；一致性检查会检测未重新生成的工作流。

需要较大调整时，可以先在独立临时目录中修改上游文件的副本，再使用
`git diff` 重新制作补丁。补丁的文件头应为
`a/.github/workflows/WRT-CORE.yml` 和 `b/.github/workflows/WRT-CORE.yml`。
