# Panther X2：VIKINGYFY 用户空间 + ophub 硬件适配

## 使用

Actions → Panther-X2-OPhub-OWRT → Run workflow。插件全部采用构建时 VIKINGYFY/OpenWRT-CI main 的 Config/GENERAL.txt，以及同一提交的 Packages.sh、Handles.sh、Settings.sh。默认主题从该提交的 OWRT-ALL.yml 读取（当前为 aurora），随上游更新。取消额外 PACKAGE 输入，不混入 fork 的 PRIVATE 配置。这里的“全部”指上游默认选中的插件，未选中的可选插件不会额外强制安装。

推送本流程相关文件只运行 validate（固定资源接入和语法校验），不会自动编译或发布。手动运行会先编译内核，再编译 rootfs 并打包，成功后上传 Artifact 和正式 Release 固件。

本流程替代已删除的 Panther-X2-Native 和 Panther-X2-Check，不使用 LEDE DTS/U-Boot 移植。Config/Panther-X2-OPhub.txt 最后应用，强制 armsr/armv8 generic 和 rootfs.tar.gz 输出；原生 Rockchip 设备配置不参与。

## 来源

- 用户空间：每次获取 VIKINGYFY/immortalwrt 的最新 owrt 分支，记录实际提交。
- 插件配置：每次独立获取 VIKINGYFY/OpenWRT-CI main 快照，记录提交；上游脚本在隔离的配置目录下运行。
- ophub 打包器：028c444dbdb74b1d005affc707cb4cf8adc922a1。
- 内核：从 Lemonade-22/ophub-kernel 的固定提交读取 stable/config-6.18，应用本仓库 prepare_kernel.py 中的 BTF/eBPF 配置，再调用固定提交的 ophub 编译工具构建 6.18.51（关闭自动升级）。内核、模块、DTB 同批生成，经本次 Actions Artifact 传递并校验 SHA256；不下载旧的 ophub/kernel Release。
- U-Boot、Armbian 启动资源、firmware、安装升级脚本：sources.json 中各自固定提交。

pin_ophub.py 将打包器的依赖下载函数改为获取这些固定提交，并禁止内核缺失时回退到远程下载，不修改分区、内核替换、Panther X2 设备选择或启动脚本。发现新增依赖或下载函数结构变化时直接失败，需人工审查锁定配置。

ophub 使用 Panther X2 专用 idbloader.img 与 u-boot.itb，独立内核、配套模块和 DTB，以及 armbianEnv.txt/boot.scr。BOOT/ROOTFS 大小传入 384/1280 MiB，分区和文件系统按锁定的 remake 原有规则生成。VIKINGYFY 的内核模块和硬件加速特性不会因此自动保留；ophub 会替换 rootfs 的内核模块。

## 验证与追踪

构建会核对上游选中的 LuCI 插件和主题，若 make defconfig 丢弃任何选项则停止。产物额外保留 upstream-plugin-config.tar.gz 和 upstream-luci-selected.config，便于核对实际使用的上游配置。

产物附带 rootfs-build.config、immortalwrt-commit.txt、feed-commits.txt、ophub-sources.json、build-info.txt、bootloader-sha256sums.txt 和 SHA256SUMS。

仓库维护者已确认 2026.09.17-10.44.03 版本可用，该版本已转为正式 Release。后续构建使用相同发布格式，配置为 Panther X2，平台为 armsr/armv8。

RKDevTool 不会自动解压 .img.gz，使用前需解压为整盘 .img；不能当单个分区镜像写入。不要从旧 Native 镜像保留配置直接升级到本布局。默认 LAN 地址 192.168.10.1；账号与密码以最终 rootfs/ophub 的实际设置为准。

## 更新

CI 仓库仍通过现有 sync-upstream.yml 合并上游，用户空间每次跟随 owrt；硬件资源不会随同步自动漂移。更新 sources.json 时核对配置仓库提交、编译工具提交与内核版本；更新打包器还需同步工作流 OPHUB_COMMIT，并重新验证。

## QMI 驱动冲突处理

X2 配置禁用 kmod-usb-net-qmi-wwan-fibocom 与 kmod-usb-net-qmi-wwan-quectel，保留 QModem 依赖的 kmod-qmi_wwan_f / kmod-qmi_wwan_q。这两组包分别提供同名模块，不能同时安装到 rootfs。只调整重复的内核驱动，不删除 LuCI 插件或主题；最终内核模块仍由 ophub 替换，蜂窝网卡功能需按最终内核实测。

配置展开后检查重复驱动是否被依赖重新启用，避免到编译末尾才报文件冲突。失败时也上传已生成的配置文件，便于排查。

## 自编译内核

配置来源为你的 ophub-kernel fork；编译任务运行在本仓库的 Panther-X2-OPhub-OWRT 工作流，不需要跨仓库 Token 或预先发布内核。每次手动构建会重新编译内核，复用 ccache；kernel 任务通过后，build 任务才开始。Artifact `panther-x2-kernel` 保留 30 天，包含内核包、SHA256、请求配置与来源记录。

编译前保留 fork 模板的硬件驱动设置，仅覆盖 BTF/eBPF 所需配置。编译后检查实际配置、模块文件和 rk3566-panther-x2.dtb，缺失则停止。固定工具提交及模板提交不代表其 Docker 镜像、工具链和下载到的内核源码完全冻结；首次构建仍需验证启动、网口、存储和 dae/daed。修改版本系列时需同步工作流中的 config-6.18 路径。
