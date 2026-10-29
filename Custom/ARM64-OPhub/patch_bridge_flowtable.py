"""Probe optional bridge offload before including it in fw4's atomic ruleset."""

import sys
from pathlib import Path


path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
old = "\t\treturn sort(uniq(bridge_devs));"
new = r'''		bridge_devs = sort(uniq(bridge_devs));

		if (!length(bridge_devs))
			return bridge_devs;

		// ARM64: a rejected bridge flowtable must not retain stale LAN rules.
		// Check both the table and expression, with the flags actually emitted.
		let probe = `
			add table bridge fw4-bridge-offload-test;
			add flowtable bridge fw4-bridge-offload-test fb {
				hook ingress priority 0;
				devices = ${this.set(bridge_devs, true)};
				counter;
				${this.default_option("flow_offloading_hw") ? "flags offload;" : ""}
			}
			add chain bridge fw4-bridge-offload-test forward {
				type filter hook forward priority filter; policy accept;
				meta l4proto { tcp, udp } flow offload @fb;
			}
		`;

		if (system(sprintf("/usr/sbin/nft -c '%s' 2>/dev/null",
		                   replace(probe, "'", "'\\''"))) != 0) {
			this.warn('Bridge flow offloading unavailable for current devices; skipping bridge offload to update firewall rules');
			return [];
		}

		return bridge_devs;'''

if source.count(old) != 1:
    raise SystemExit("Expected one bridge device return in fw4.uc")
path.write_text(source.replace(old, new), encoding="utf-8")
