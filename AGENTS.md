# 给后续 AI 的规矩

本仓是 `Lemonade-22/OpenWRT-CI_Self`：用 GitHub Actions 编 ImmortalWrt 固件。
下面这些是踩过的坑，不是建议。

## 一、给路由器装包，先走 op-joshu，别用 ssh 手敲

`ssh` 是**最后手段**，用于改配置、读日志、排查故障。**装包不是它的活。**

正确的顺序：

```
op_joshu_detect     平台、架构、包管理器、剩余空间
op_joshu_search     软件源里有没有（按设备架构推导该搜哪些目录）
op_joshu_assets     源里没有，就去 GitHub release 找对应架构的包
op_joshu_install    本地下载 → 传到设备 → apk/opkg 正规安装
op_joshu_installed  核对装上了没
```

### 关键事实：下载发生在你的机器上

`op_joshu_install` 的 `urls` 是"包的直接下载地址"，**下载在 MCP 主机侧完成**，
然后把文件传过去本地安装。整条链路**不依赖目标设备能否访问外网**。

所以设备"没默认路由、ping 不通、DNS 全 REFUSED"这些都不能作为"装不了包"的
理由。只看一件事：SSH 通不通。

同理 `op_joshu_search` 的 `host` 参数是"现场探测设备以推导架构目录"，搜索本身
不算设备出网。

（这条规矩就是因为我犯过一次：查到 `wan@eth0` NO-CARRIER 就断言装不了，
绕了三轮 ssh 手敲，而 `install` 一次就能成。）

## 二、改动分两支，别混

| 分支 | 放什么 | 从它触发 |
| --- | --- | --- |
| `main` | 主战场。honk 支持、通用的 CI 修复 | 绝大多数机型 |
| `multiwifi` | N60 Pro 的多WIFI / passwall2 定制 | 只有 N60 Pro Multi |

`multiwifi` 是从 `main` 拉出来的，`main` 往前走它不会自动跟。改完 `main` 记得
rebase 一次，否则越落越远。

## 三、Passwall2 / 多WIFI 的东西只准留在 multiwifi 分支

包括 `Custom/multiwifi/**`、`Config/N60-Pro-512M-WIFI-Multi.txt`、
`Scripts/Device-Hooks/N60-Pro-512M-WIFI-Multi.sh`。

`Scripts/Packages.sh` 里 `UPDATE_PACKAGE "passwall2"` 那行是**上游原有**的，
不是我们加的，别动。

## 四、内核开关别写 `CONFIG_KERNEL_*`

写进 `.config` 会被 `make defconfig` 静默丢弃——kconfig 判定依赖不可满足就整条扔掉，
零警告。

正路是 `Scripts/kernel_compat.py`：它把符号注册进 `config/Config-kernel.in`，
defconfig 之后才留得住。要加新符号，扩展这个脚本的 `declarations()`。

honk 需要的 `NET_CLS_ACT` + `NET_XGRESS` 就是这么开的，ramips 除外（内核 6.6）。

## 五、Windows 上的两个坑

- `core.autocrlf` 保持 `false`。shell 脚本带 CRLF 到路由器上直接 `bad interpreter`。
- 测试脚本调 bash 别写裸 `bash`，会摸到 System32 的 WSL 启动器。用 Git 的
  `usr/bin/bash.exe` 全路径。
