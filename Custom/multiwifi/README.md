# 多WIFI

把一块 MT7986A 的两个 phy 切成最多 32 个互相隔离的 SSID，每个 SSID 一个独立
网段、独立 DHCP、独立出口节点。

## 它到底是什么

不是固件特性，不是内核补丁，不是驱动魔改。原机（TikTok-Yemaowrt，OpenWrt
24.10.3 / MT7986A）拆开之后，kernel 和 rootfs 跟 ImmortalWrt 官方包 sha256
完全一致，全部改动都在 NAND 的 rootfs_data 里，就是一堆 UCI：

| 层 | 内容 |
| --- | --- |
| 射频 | 每 phy 15 个副 BSS + 1 个主 BSS，打满 if_limits.max=16 |
| 网络 | wifi01..wifi30，188.181.N.1/24，各一段 DHCP |
| 隔离 | isolate=1 + macaddr=random（每次起来换 BSSID） |
| 出口 | passwall2 的 _shunt，30 条 shunt_rules 各带 source=188.181.N.0/24 |

## 怎么用

    # 生成
    sh /etc/uci-defaults/97-multiwifi

    # 想重排：改 /etc/multiwifi.conf 后
    rm /etc/config/wireless && reboot

参数在 /etc/multiwifi.conf，CI 里由 Device-Hooks/N60-Pro-512M-WIFI-Multi.sh
按 workflow 的 WRT_SSID / WRT_WORD 覆写前缀和密码。

## 出口节点

生成出来的 30 条 shunt_rules 出口是空的，全部跟随默认节点。要一网段一个 IP，
去 LuCI 的 PassWall2 → 节点 → 总开关（勿删），逐条把 wifi-01…wifi-30 指到自己的节点。

原机是拿 26 个 iepl01.huojianip.com 的美国独享 IP 填的，那家的凭据在配置里
明文躺着——这份实现里一条都没带。

## 跟原机不一样的地方

- forward 从 ACCEPT 改成 REJECT：原机 30 个网段在同一个 zone 里互相能扫通，
  跨 SSID 完全没隔离
- 没带任何节点凭据
- use_nft 默认走 nftables（目标固件是 firewall4）；原机是 iptables 模式
