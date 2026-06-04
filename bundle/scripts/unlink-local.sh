#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$BUNDLE_ROOT/manifest.yaml"
DRY_RUN=0
ONLY="all"

usage() { echo "Usage: unlink-local.sh [--dry-run] [--only claude|opencode|codex|cursor]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --only) shift; ONLY="${1:-}"; case "$ONLY" in claude|opencode|codex|cursor) ;; *) echo "invalid --only: $ONLY" >&2; exit 2 ;; esac ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 - "$MANIFEST" "$BUNDLE_ROOT" "$DRY_RUN" "$ONLY" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
bundle_root = Path(sys.argv[2]).resolve()
dry = sys.argv[3] == "1"
only = sys.argv[4]


def unquote(value: str) -> str:
    value = value.strip()
    return value[1:-1] if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0] else value


def parse(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_links = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "links:":
            in_links = True
            continue
        if not in_links:
            continue
        if line.startswith("  - "):
            if current:
                entries.append(current)
            current = {}
            rest = line[4:].strip()
            if rest:
                key, _, value = rest.partition(":")
                current[key.strip()] = unquote(value.strip())
        elif current is not None and line.startswith("    "):
            key, _, value = stripped.partition(":")
            current[key.strip()] = unquote(value.strip())
    if current:
        entries.append(current)
    return entries


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


removed = 0
skipped = 0
errors = 0
for entry in parse(manifest_path):
    platform = entry.get("platform", "shared")
    if only != "all" and platform != only:
        continue
    src_value = entry.get("src")
    dest_value = entry.get("dest")
    if not src_value or not dest_value:
        print(f"ERROR manifest entry missing src/dest: {entry}", file=sys.stderr)
        errors += 1
        continue
    expected = (bundle_root / src_value).resolve(strict=False)
    if not is_relative_to(expected, bundle_root):
        print(f"ERROR source escapes bundle: {src_value} -> {expected}", file=sys.stderr)
        errors += 1
        continue
    dest = Path(os.path.expandvars(os.path.expanduser(dest_value)))
    if not dest.is_symlink():
        print(f"SKIP not a symlink: {dest}")
        skipped += 1
        continue
    target = dest.resolve(strict=False)
    if target != expected:
        print(f"SKIP symlink not owned by manifest entry: {dest} -> {target}; expected {expected}")
        skipped += 1
        continue
    if dry:
        print(f"DRY-RUN unlink {dest} -> {target}")
    else:
        dest.unlink()
        print(f"UNLINK {dest}")
    removed += 1
if errors:
    raise SystemExit(1)
print(f"summary: removed_or_would_remove={removed} skipped={skipped} dry_run={dry} only={only}")
PY
