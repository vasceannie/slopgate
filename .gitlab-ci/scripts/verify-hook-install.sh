#!/usr/bin/env bash
# verify-hook-install.sh — verify slopgate hooks were installed into
# each harness config. Handles both flat {command:...} and nested
# {hooks:[{type:command, command:...}]} formats.
set -euo pipefail

platform="$1"

case "$platform" in
  claude)
    config="$HOME/.claude/settings.json"
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
