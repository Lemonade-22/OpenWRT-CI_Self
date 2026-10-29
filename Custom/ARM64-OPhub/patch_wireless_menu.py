"""Keep wireless management accessible before late radio configuration exists."""

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
menu = json.loads(path.read_text(encoding="utf-8"))
depends = menu["admin/network/wireless"]["depends"]
depends.pop("uci", None)
depends["fs"] = {"/sbin/wifi": "executable"}
path.write_text(json.dumps(menu, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")
