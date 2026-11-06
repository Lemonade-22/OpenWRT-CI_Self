# Preinstalled theme source

`Scripts/Check-Preinstalled.sh prepare` runs in the OpenWrt source tree after
package customization and theme resolution, before Settings.sh and defconfig.
All shared build routes and the three standalone device workflows call it,
including MT7621 and OPhub rootfs builds.

If the selected theme has no Makefile, the script downloads vantage from
anothaDev/luci-theme-vantage (main), or asks the configured feeds to install the
selected theme. Existing sources are reused. Unknown external sources must be
added explicitly rather than guessed. To add automatic recovery for another
external theme, add its repository to the prepare case statement.

There is no rootfs package dry run. An earlier version installed a hook in
OpenWrt's package/Makefile that re-ran the rootfs transaction with APK
--simulate or OPKG --noaction. That hook was removed: APK --simulate skips the
database bootstrap that --initdb performs and cannot read a fresh rootfs, and
seeding the layout by hand did not survive a real build. A missing package or
dependency now surfaces at install time rather than before it.
