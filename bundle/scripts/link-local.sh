#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$BUNDLE_ROOT/manifest.yaml"
DRY_RUN=0
FORCE=0
ONLY="all"

usage() {
  cat <<'USAGE'
Usage: link-local.sh [--dry-run] [--force] [--only claude|opencode|codex|cursor]

Create symlinks declared in bundle/manifest.yaml. This script never owns live
hooks.json/settings.json hook commands; run `slopgate install ...` for hooks.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    --only)
      shift
      ONLY="${1:-}"
      case "$ONLY" in claude|opencode|codex|cursor) ;; *) echo "invalid --only: $ONLY" >&2; exit 2 ;; esac
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 - "$MANIFEST" "$BUNDLE_ROOT" "$DRY_RUN" "$FORCE" "$ONLY" <<'PY'
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

manifest_path = Path(sys.argv[1])
bundle_root = Path(sys.argv[2]).resolve()
dry_run = sys.argv[3] == "1"
force = sys.argv[4] == "1"
only = sys.argv[5]

FORBIDDEN_DEST_NAMES = {"hooks.json", "settings.json", "CLAUDE.md", "AGENTS.md"}
FORBIDDEN_DEST_SUFFIXES = {".claude/settings.json", ".cursor/hooks.json", ".codex/hooks.json"}

def unquote(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value

def parse_key_value(text: str) -> tuple[str, str]:
    key, sep, value = text.partition(':')
    if not sep:
        raise ValueError(f"manifest line is not key: value: {text!r}")
    return key.strip(), unquote(value.strip())

def parse_manifest(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_links = False
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped == 'links:':
            in_links = True
            continue
        if not in_links:
            continue
        if line.startswith('  - '):
            if current:
                entries.append(current)
            current = {}
            rest = line[4:].strip()
            if rest:
                key, value = parse_key_value(rest)
                current[key] = value
            continue
        if current is not None and line.startswith('    '):
            key, value = parse_key_value(stripped)
            current[key] = value
    if current:
        entries.append(current)
    return entries

def infer_platform(entry: dict[str, str]) -> str:
    if entry.get('platform'):
        return entry['platform']
    haystack = f"{entry.get('src','')} {entry.get('dest','')}".lower()
    for platform in ("claude", "opencode", "codex", "cursor"):
        if platform in haystack:
            return platform
    return "shared"

def is_forbidden_dest(dest: Path) -> bool:
    expanded = str(dest.expanduser())
    return dest.name in FORBIDDEN_DEST_NAMES or any(expanded.endswith(suffix) for suffix in FORBIDDEN_DEST_SUFFIXES)

entries = parse_manifest(manifest_path)
if not entries:
    raise SystemExit(f"no links found in {manifest_path}")

errors = 0
linked = 0
skipped = 0
for entry in entries:
    platform = infer_platform(entry)
    if only != 'all' and platform != only:
        continue
    src_value = entry.get('src')
    dest_value = entry.get('dest')
    if not src_value or not dest_value:
        print(f"ERROR manifest entry missing src/dest: {entry}", file=sys.stderr)
        errors += 1
        continue
    src = (bundle_root / src_value).resolve(strict=False)
    try:
        src.relative_to(bundle_root)
    except ValueError:
        print(f"ERROR source escapes bundle: {src_value} -> {src}", file=sys.stderr)
        errors += 1
        continue
    dest = Path(os.path.expandvars(os.path.expanduser(dest_value)))
    if is_forbidden_dest(dest):
        print(f"SKIP forbidden full harness config target: {dest}")
        skipped += 1
        continue
    if not src.exists():
        print(f"ERROR missing source: {src}", file=sys.stderr)
        errors += 1
        continue
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink():
            current = dest.resolve(strict=False)
            if current == src:
                print(f"OK already linked: {dest} -> {src}")
                linked += 1
                continue
            if not force:
                print(f"SKIP existing symlink not owned by this bundle: {dest} -> {current} (use --force)")
                skipped += 1
                continue
            action = f"replace symlink {dest} -> {src}"
            if dry_run:
                print(f"DRY-RUN {action}")
                linked += 1
                continue
            dest.unlink()
        else:
            if not force:
                print(f"SKIP existing real path: {dest} (use --force after review)")
                skipped += 1
                continue
            backup = dest.with_name(f"{dest.name}.bundle-backup-{time.strftime('%Y%m%d-%H%M%S')}")
            action = f"move {dest} to {backup}, then link -> {src}"
            if dry_run:
                print(f"DRY-RUN {action}")
                linked += 1
                continue
            dest.rename(backup)
            print(f"BACKUP {dest} -> {backup}")
    action = f"link {dest} -> {src}"
    if dry_run:
        print(f"DRY-RUN {action}")
        linked += 1
        continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(src, dest, target_is_directory=src.is_dir())
    print(f"LINK {dest} -> {src}")
    linked += 1

if errors:
    raise SystemExit(1)
print(f"summary: linked_or_ok={linked} skipped={skipped} dry_run={dry_run} force={force} only={only}")
print("next: slopgate install all  # hook files stay owned by the CLI installer")
PY
