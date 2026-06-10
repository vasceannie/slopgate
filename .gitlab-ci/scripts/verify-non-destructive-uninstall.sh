#!/usr/bin/env bash
# verify-non-destructive-uninstall.sh — test that uninstalling slopgate
# hooks does not remove user-added hooks.
# Creates harness configs pre-populated with user hooks, installs
# slopgate hooks (merge), then uninstalls and verifies user hooks survive.
set -euo pipefail

TEST_HOME="$1"
rm -rf "$TEST_HOME" && mkdir -p "$TEST_HOME"

# Create harness configs with user hooks
mkdir -p "$TEST_HOME/.claude" "$TEST_HOME/.codex" "$TEST_HOME/.cursor" "$TEST_HOME/.config/opencode/plugins"

python3 <<PYEOF
import json, pathlib
h = "$TEST_HOME"
# Claude with user hooks (flat format)
d = {'hooks': {'PreToolUse': [{'command': 'echo claude-user-pre', 'timeout': 5000}],
               'PostToolUse': [{'command': 'echo claude-user-post', 'timeout': 5000}]}}
pathlib.Path(h + '/.claude/settings.json').write_text(json.dumps(d, indent=2))
# Codex with user hooks (flat format)
d = {'hooks': {'PreToolUse': [{'command': 'echo codex-user-hook', 'timeout': 5000}]}}
pathlib.Path(h + '/.codex/hooks.json').write_text(json.dumps(d, indent=2))
# Cursor with user hooks (flat format)
d = {'hooks': {'PreToolUse': [{'command': 'echo cursor-user-hook', 'timeout': 5000}]}}
pathlib.Path(h + '/.cursor/hooks.json').write_text(json.dumps(d, indent=2))
PYEOF

export HOME="$TEST_HOME"

echo "=== 1. Verify baseline user hooks ==="
python3 <<PYEOF
import json, pathlib

def extract_commands(entries):
    cmds = []
    for entry in entries if entries else []:
        if not isinstance(entry, dict):
            continue
        flat = entry.get("command")
        if isinstance(flat, str):
            cmds.append(flat)
        nested = entry.get("hooks", [])
        if isinstance(nested, list):
            for h in nested:
                if isinstance(h, dict):
                    c = h.get("command")
                    if isinstance(c, str):
                        cmds.append(c)
    return cmds

for name, path in [("Claude", "$HOME/.claude/settings.json"),
                    ("Codex", "$HOME/.codex/hooks.json"),
                    ("Cursor", "$HOME/.cursor/hooks.json")]:
    data = json.loads(pathlib.Path(path).read_text())
    all_entries = []
    for entries in data.get("hooks", {}).values():
        all_entries.extend(entries)
    cmds = extract_commands(all_entries)
    user_cmds = [c for c in cmds if "user" in c]
    print(f"  {name}: {len(user_cmds)} user hook(s)")
    assert user_cmds, f"Missing user hooks in {name}!"
print("  OK baseline")
PYEOF

echo ""
echo "=== 2. Install slopgate hooks ==="
slopgate install all --install-scope user --disable-autoupdate

echo ""
echo "=== 3. Verify merge: user + slopgate hooks coexist ==="
python3 <<PYEOF
import json, pathlib

def extract_commands(entries):
    cmds = []
    for entry in entries if entries else []:
        if not isinstance(entry, dict):
            continue
        flat = entry.get("command")
        if isinstance(flat, str):
            cmds.append(flat)
        nested = entry.get("hooks", [])
        if isinstance(nested, list):
            for h in nested:
                if isinstance(h, dict):
                    c = h.get("command")
                    if isinstance(c, str):
                        cmds.append(c)
    return cmds

for name, path in [("Claude", "$HOME/.claude/settings.json"),
                    ("Codex", "$HOME/.codex/hooks.json"),
                    ("Cursor", "$HOME/.cursor/hooks.json")]:
    data = json.loads(pathlib.Path(path).read_text())
    all_entries = []
    for entries in data.get("hooks", {}).values():
        all_entries.extend(entries)
    cmds = extract_commands(all_entries)
    user_cmds = [c for c in cmds if "user" in c]
    slopgate_cmds = [c for c in cmds if "slopgate" in c or "handle" in c]
    print(f"  {name}: {len(user_cmds)} user, {len(slopgate_cmds)} slopgate")
    assert user_cmds, f"User hooks LOST during install in {name}!"
    assert slopgate_cmds, f"No slopgate hooks in {name}!"
print("  OK merge")
PYEOF

echo ""
echo "=== 4. Uninstall slopgate hooks ==="
slopgate uninstall all --disable-autoupdate

echo ""
echo "=== 5. Verify non-destructive: user hooks survive ==="
python3 <<PYEOF
import json, pathlib

def extract_commands(entries):
    cmds = []
    for entry in entries if entries else []:
        if not isinstance(entry, dict):
            continue
        flat = entry.get("command")
        if isinstance(flat, str):
            cmds.append(flat)
        nested = entry.get("hooks", [])
        if isinstance(nested, list):
            for h in nested:
                if isinstance(h, dict):
                    c = h.get("command")
                    if isinstance(c, str):
                        cmds.append(c)
    return cmds

for name, path in [("Claude", "$HOME/.claude/settings.json"),
                    ("Codex", "$HOME/.codex/hooks.json"),
                    ("Cursor", "$HOME/.cursor/hooks.json")]:
    data = json.loads(pathlib.Path(path).read_text())
    hooks = data.get("hooks", {})
    all_entries = []
    for entries in hooks.values():
        all_entries.extend(entries)
    cmds = extract_commands(all_entries)
    user_cmds = [c for c in cmds if "user" in c]
    slopgate_cmds = [c for c in cmds if "slopgate" in c or "handle" in c]
    print(f"  {name}: {len(user_cmds)} user, {len(slopgate_cmds)} slopgate")
    assert user_cmds, f"User hooks REMOVED by uninstall in {name}!"
    assert not slopgate_cmds, f"Slopgate hooks survived uninstall in {name}!"
print("  OK non-destructive uninstall")
PYEOF

echo ""
echo "=== 6. Verify uninstall is idempotent ==="
slopgate uninstall all --disable-autoupdate || true
echo "  OK idempotent"
