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
import os, sys
from pathlib import Path
manifest_path = Path(sys.argv[1]); bundle_root = Path(sys.argv[2]).resolve(); dry = sys.argv[3] == '1'; only = sys.argv[4]
def unquote(v: str) -> str:
    v=v.strip(); return v[1:-1] if len(v)>=2 and v[0] in "'\"" and v[-1] == v[0] else v
def parse(path: Path):
    entries=[]; cur=None; in_links=False
    for raw in path.read_text(encoding='utf-8').splitlines():
        line=raw.rstrip(); s=line.strip()
        if not s or s.startswith('#'): continue
        if s == 'links:': in_links=True; continue
        if not in_links: continue
        if line.startswith('  - '):
            if cur: entries.append(cur)
            cur={}; rest=line[4:].strip()
            if rest:
                k,_,v=rest.partition(':'); cur[k.strip()]=unquote(v.strip())
        elif cur is not None and line.startswith('    '):
            k,_,v=s.partition(':'); cur[k.strip()]=unquote(v.strip())
    if cur: entries.append(cur)
    return entries
removed=skipped=0
for e in parse(manifest_path):
    platform=e.get('platform','shared')
    if only != 'all' and platform != only: continue
    dest=Path(os.path.expandvars(os.path.expanduser(e['dest'])))
    if not dest.is_symlink():
        print(f"SKIP not a symlink: {dest}"); skipped += 1; continue
    target=dest.resolve(strict=False)
    try:
        target.relative_to(bundle_root)
    except ValueError:
        print(f"SKIP symlink not owned by bundle: {dest} -> {target}"); skipped += 1; continue
    if dry:
        print(f"DRY-RUN unlink {dest} -> {target}")
    else:
        dest.unlink(); print(f"UNLINK {dest}")
    removed += 1
print(f"summary: removed_or_would_remove={removed} skipped={skipped} dry_run={dry} only={only}")
PY
