#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_ROOT="$BUNDLE_ROOT/claude-plugin"
MODE="link"

usage() { echo "Usage: build-claude-plugin.sh [--link|--copy]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --link) MODE="link" ;;
    --copy) MODE="copy" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$PLUGIN_ROOT/skills" "$PLUGIN_ROOT/agents" "$PLUGIN_ROOT/hooks"

populate_one() {
  local src="$1" dest="$2"
  if [[ -e "$dest" || -L "$dest" ]]; then
    rm -rf "$dest"
  fi
  if [[ "$MODE" == "copy" ]]; then
    cp -a "$src" "$dest"
  else
    local rel_src
    rel_src="$(python3 - "$src" "$(dirname "$dest")" <<'PY'
from pathlib import Path
import os
import sys
print(os.path.relpath(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
PY
)"
    ln -s "$rel_src" "$dest"
  fi
}

for skill in "$BUNDLE_ROOT"/shared/skills/*; do
  [[ -e "$skill" ]] || continue
  populate_one "$skill" "$PLUGIN_ROOT/skills/$(basename "$skill")"
done
for agent in "$BUNDLE_ROOT"/claude/agents/*.md; do
  [[ -e "$agent" ]] || continue
  populate_one "$agent" "$PLUGIN_ROOT/agents/$(basename "$agent")"
done

printf 'built Claude plugin component tree at %s using mode=%s\n' "$PLUGIN_ROOT" "$MODE"
printf 'test locally: claude --plugin-dir %q\n' "$PLUGIN_ROOT"
