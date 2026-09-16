# Panther X2：VIKINGYFY 用户空间 + ophub 硬件适配

## 使用

Actions → Panther-X2-OPhub-OWRT → Run workflow。PACKAGE 可填写额外软件包选项；留空沿用 Config/GENERAL.txt 和仓库现有 Packages.sh、Handles.sh、Settings.sh 定制。

推送本流程相关文件只运行 validate（固定资源接入和语法校验），不会自动编译或发布。手动运行才会编译 rootfs 并打包，成功后上传 Artifact 和标为 prerelease 的测试固件。

本流程替代已删除的 Panther-X2-Native 和 Panther-X2-Check，不使用 LEDE DTS/U-Boot 移植。Config/Panther-X2-OPhub.txt 最后应用，强制 armsr/armv8 generic 和 rootfs.tar.gz 输出；原生 Rockchip 设备配置不参与。

## 来源

- 用户空间：每次获取 VIKINGYFY/immortalwrt 的最新 owrt 分支，记录实际提交。
- ophub 打包器：028c444dbdb74b1d005affc707cb4cf8adc922a1。
- 内核：ophub/kernel 的 kernel_stable/6.18.51.tar.gz；下载后比对 sources.json 的 SHA256，再交由原打包器校验内部文件。
- U-Boot、Armbian 启动资源、firmware、安装升级脚本：sources.json 中各自固定提交。

pin_ophub.py 只将打包器的依赖下载函数改为获取这些固定提交，不修改分区、内核替换、Panther X2 设备选择或启动脚本。发现新增依赖或下载函数结构变化时直接失败，需人工审查锁定配置。

ophub 使用 Panther X2 专用 idbloader.img 与 u-boot.itb，独立内核、配套模块和 DTB，以及 armbianEnv.txt/boot.scr。BOOT/ROOTFS 大小传入 384/1280 MiB，分区和文件系统按锁定的 remake 原有规则生成。VIKINGYFY 的内核模块和硬件加速特性不会因此自动保留；ophub 会替换 rootfs 的内核模块。

## 验证与追踪

产物附带 rootfs-build.config、immortalwrt-commit.txt、feed-commits.txt、ophub-sources.json、build-info.txt、bootloader-sha256sums.txt 和 SHA256SUMS。

首次运行仍需完整编译及设备测试。校验 job 成功不代表固件已启动；此次硬件资源固定的是当前取得的提交，并非已经逐字节复现某个历史发布镜像。验证启动、网口、存储及插件后再将测试版视为可用版本。

RKDevTool 不会自动解压 .img.gz，使用前需解压为整盘 .img；不能当单个分区镜像写入。不要从旧 Native 镜像保留配置直接升级到本布局。默认 LAN 地址 192.168.10.1；账号与密码以最终 rootfs/ophub 的实际设置为准。

## 更新

CI 仓库仍通过现有 sync-upstream.yml 合并上游，用户空间每次跟随 owrt；硬件资源不会随同步自动漂移。更新 sources.json 时核对提交与内核 SHA256；更新打包器还需同步工作流 OPHUB_COMMIT，并重新验证。
