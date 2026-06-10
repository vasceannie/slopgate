#!/usr/bin/env bash
# verify-opencode-plugin.sh — verify rendered OpenCode plugin uses a safe argv
# prefix and cannot degrade into `python handle ...` when SLOPGATE_BIN points to
# a Python interpreter.
set -euo pipefail

export SLOPGATE_OPENCODE_PLUGIN_PATH="${1:-$HOME/.config/opencode/plugins/slopgate-plugin.ts}"

python3 <<'PYEOF'
import os
import pathlib
import re
import sys

p = pathlib.Path(os.environ["SLOPGATE_OPENCODE_PLUGIN_PATH"])
if not p.exists():
    print(f"MISSING: {p}")
    sys.exit(1)
text = p.read_text(encoding="utf-8", errors="replace")
checks = {
    "placeholder removed": "__SLOPGATE_BIN__" not in text,
    "argv fallback constant": "const SLOPGATE_ARGV" in text,
    "spawn uses argv spread": '[...SLOPGATE_ARGV, "handle", "--platform", "opencode"]' in text,
    "legacy single binary spawn removed": '[SLOPGATE_BIN, "handle", "--platform", "opencode"]' not in text,
}
for name, ok in checks.items():
    print(f"{name}: {'OK' if ok else 'FAIL'}")
    if not ok:
        sys.exit(1)

# Catch the exact broken shape seen in production: a Python executable as the
# only argv element, followed by handle instead of -m slopgate handle.
bad_python_handle = re.search(
    r'SLOPGATE_ARGV\s*=\s*\[[^\]]*python[^\]]*\][\s\S]*?\[\.\.\.SLOPGATE_ARGV,\s*"handle"',
    text,
    re.IGNORECASE,
)
if bad_python_handle and '"-m", "slopgate"' not in text:
    print("bad python handle argv: FAIL")
    sys.exit(1)
print("bad python handle argv: OK")
PYEOF
