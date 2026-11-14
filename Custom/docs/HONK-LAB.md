# honk 实验机上手指南

适用于 `ZN-M2-WIFI-NO` 和 `XG-040G-MD-NATIVE`。**两台固件都不再内置 `luci-app-honk`**，
前端和 `honk-core` 都要自己装：前端见第 1 步，`honk-core` 见第 2 步。

## 1. 装前端（luci-app-honk）

这个仓库只为 `dae`/`daed` 出包，`luci-app-honk` 不再自动编译。源码在
`Lemonade-22/packages` 的 `luci-app-honk` 目录，用 SDK 编一次，或者直接装编好的包：

```sh
apk add --allow-untrusted ./luci-app-honk-*.apk    # apk 系统（25.12+）
opkg install ./luci-app-honk-*.ipk                 # opkg 系统
apk info -e luci-app-honk                          # 装完确认
```

装上了，LuCI 的「服务」下才会出现 **Honk**。

## 2. 装 honk-core

```sh
wget -O /etc/apk/keys/daeuniverse.pem https://openwrt.daeuniverse.org/public-key.pem
. /etc/openwrt_release
FEED="https://openwrt.daeuniverse.org/$(echo $DISTRIB_RELEASE | cut -d. -f1-2)"
echo "$FEED/packages.adb" >> /etc/apk/repositories.d/daeuniverse.list
apk update
apk add honk vmlinux-btf-builtin
```

`vmlinux-btf-builtin` 是空包，因为 ImmortalWrt 内核自带 BTF
（`CONFIG_KERNEL_DEBUG_INFO_BTF=y`）。如果是官方 OpenWrt 内核，改装 `vmlinux-btf`。

装完先看它认不认内核：

```sh
honk-core --version
ls -l /sys/kernel/btf/vmlinux    # 必须存在
```

## 3. 首要验证：TCX 到底开没开

这是整个实验里最容易失败的一环，**先验它再折腾配置**：

```sh
zcat /proc/config.gz | grep -E "^CONFIG_(NET_CLS_ACT|NET_XGRESS)="
# 或者，没有 config.gz 时：
strings /boot/vmlinux 2>/dev/null | grep -m1 NET_XGRESS
```

要看到 `CONFIG_NET_CLS_ACT=y` 和 `CONFIG_NET_XGRESS=y`。缺任何一个，honk 起来会
在 attach 阶段失败，而且报错未必直观。

## 4. 最小可用配置

1. LuCI → 服务 → Honk → **节点与组**：加一个节点（分享链接），再建一个组，
   成员勾上那个节点。
2. **路由设置**：启用，主节点选那个组，路由模式选「绕过中国大陆」。
3. 保存。UCI 变更会自动触发 `/etc/init.d/honk reload`。

命令行核对：

```sh
/etc/init.d/honk reload
cat /etc/honk/config.dae          # 看生成的规则对不对
logread -e honk | tail -30
```

## 5. 出问题时按这个顺序查

| 现象 | 先看哪里 |
| --- | --- |
| 服务起不来 | `logread -e honk`；八成是 `/var/lib/honk` 权限不是 700 |
| 起来了但不通 | 组里有没有节点；`config.dae` 的 `fallback` 指向谁 |
| 大陆域名也走代理 | `geosite.dat` / `geoip.dat` 在不在 `/usr/share/honk/geo/` |
| 全部流量都断 | `ipversion(6) -> block` 且客户端只走 v6；改成 direct 试试 |
| DNS 不生效 | honk 的透明 DNS 和 dnsmasq 抢 53；`logread` 里找 DNS 相关行 |

## 6. 两台的差异

- **ZN-M2**：qualcommax/ipq60xx，PPE 版走 VIKINGYFY 的 `owrt` 分支，内核 6.18。
- **XG-040G-MD**：airoha/an7581，自带 `kernel_compat.py` 的严格内核校验，
  编译期就会断言 `NET_CLS_ACT` 等符号，起不来会直接构不过。
