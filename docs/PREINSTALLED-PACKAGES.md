# Preinstalled theme source

`Scripts/Check-Preinstalled.sh prepare` runs in the OpenWrt source tree right
after `Scripts/Theme.sh`, before Settings.sh and defconfig. All shared build
routes and the three standalone device workflows call it.

`Scripts/Theme.sh` resolves `WRT_THEME=auto` by reading the `WRT_THEME` value
from VIKINGYFY/OpenWRT-CI, so every device follows whatever theme upstream
ships. A concrete name in a workflow pins that device and skips the lookup.

This script makes the resolved theme buildable:

1. If `package/` or `feeds/luci` already has `luci-theme-<theme>`, it is used.
2. Otherwise the repository is looked up in `Scripts/themes.txt` and cloned
   into `package/`.
3. Otherwise the configured feeds are asked to install it.
4. Otherwise the run stops with an error naming the theme and telling you to add
   its repository to `Scripts/themes.txt`.

So an upstream theme change needs no workflow edit: the new theme is fetched and
built into the firmware. The only manual step, when the theme lives in a
repository nobody has recorded yet, is one line in `Scripts/themes.txt`.

There is no rootfs package dry run. An earlier version installed a hook in
OpenWrt's package/Makefile that re-ran the rootfs transaction with APK
--simulate or OPKG --noaction. That hook was removed: APK --simulate skips the
database bootstrap that --initdb performs and cannot read a fresh rootfs, and
seeding the layout by hand did not survive a real build. A missing package or
dependency now surfaces at install time rather than before it.
