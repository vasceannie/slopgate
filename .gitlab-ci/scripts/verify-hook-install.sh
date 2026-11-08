#!/usr/bin/env bash
# verify-hook-install.sh — verify slopgate hooks were installed into
# each harness config. Handles both flat {command:...} and nested
# {hooks:[{type:command, command:...}]} formats.
set -euo pipefail

platform="$1"

case "$platform" in
  claude)
    # Claude installs as a native plugin (registered via `claude plugin`),
    # not as hook entries in settings.json.
    if claude plugin list --json | python3 -c '
import json, sys
plugins = json.load(sys.stdin)
match = [p for p in plugins if p.get("id") == "slopgate-enforcement@slopgate-runtime"]
print(f"claude: {len(match)} slopgate plugin(s) registered")
sys.exit(0 if match and all(p.get("enabled") for p in match) else 1)
'; then
      exit 0
    fi
    echo "ERROR: slopgate-enforcement plugin not registered/enabled in Claude"
    exit 1
    ;;
  codex)
    config="$HOME/.codex/hooks.json"
    ;;
  cursor)
    config="$HOME/.cursor/hooks.json"
    ;;
  *)
    echo "Unknown platform: $platform"
    exit 1
    ;;
esac

python3 <<PYEOF
import json, pathlib, sys

def extract_commands(entries):
    """Extract all command strings from hook entries, handling both
    flat {command: ...} and nested {hooks: [{command: ...}]} formats."""
    cmds = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Flat format: {"command": "..."}
        flat = entry.get("command")
        if isinstance(flat, str):
            cmds.append(flat)
        # Nested format: {"hooks": [{"type": "command", "command": "..."}]}
        nested = entry.get("hooks", [])
        if isinstance(nested, list):
            for h in nested:
                if isinstance(h, dict):
                    c = h.get("command")
                    if isinstance(c, str):
                        cmds.append(c)
    return cmds

p = pathlib.Path("$config")
if not p.exists():
    print(f"MISSING: $config")
    sys.exit(1)
data = json.loads(p.read_text())
hooks = data.get("hooks", {})
all_cmds = []
for entries in hooks.values():
    all_cmds.extend(extract_commands(entries))
slopgate_cmds = [c for c in all_cmds if "slopgate" in c or "handle" in c]
print(f"$platform: {len(slopgate_cmds)} slopgate commands across {len(hooks)} event(s)")
if not slopgate_cmds:
    print(f"ERROR: no slopgate hook commands found in $config")
    print(f"All commands found: {all_cmds[:10]}")
    sys.exit(1)
PYEOF
