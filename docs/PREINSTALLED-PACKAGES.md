# Preinstalled package checks

`Scripts/Check-Preinstalled.sh prepare` runs in the OpenWrt source tree after
package customization and theme resolution, before Settings.sh and defconfig.
All shared build routes and the three standalone device workflows call it,
including MT7621 and OPhub rootfs builds.

If the selected theme has no Makefile, the script downloads vantage from
anothaDev/luci-theme-vantage (main), or asks the configured feeds to install the
selected theme. Existing sources are reused. Unknown external sources must be
added explicitly rather than guessed. To add automatic recovery for another
external theme, add its repository to the prepare case statement.

The script installs a hook in OpenWrt's package/Makefile. Immediately before the
rootfs package transaction, it runs the same command with APK --simulate or
OPKG --noaction. This uses the exact generated install list, local package
index/files, architecture, ABI versions and signing keys used by OpenWrt.
For a fresh APK rootfs the hook first creates the empty database directories
and world file, because APK disables --initdb during --simulate. Existing world
contents are preserved and no packages are marked installed by this bootstrap.
The package manager reports missing packages and dependency conflicts. A failed
check prevents installation; a successful check proceeds with the original
command. No runtime install scripts execute during the dry run.

This does not fetch prebuilt packages from unrelated binary repositories.
A missing source can be recovered before compilation; missing build outputs or
unknown dependencies at packaging time require correcting and rebuilding their
sources. A source branch whose installation command no longer matches the hook
fails during preparation rather than silently omitting the check.

A valid cached rootfs may be restored without a new install transaction; the
OpenWrt cache key includes its package index and package/Makefile.
