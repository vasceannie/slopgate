#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$BUNDLE_ROOT/manifest.yaml"
ONLY="all"
RUN_SLOPGATE_TEST=0

usage() { echo "Usage: verify-local.sh [--only claude|opencode|codex|cursor] [--slopgate-test]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) shift; ONLY="${1:-}"; case "$ONLY" in claude|opencode|codex|cursor) ;; *) echo "invalid --only: $ONLY" >&2; exit 2 ;; esac ;;
    --slopgate-test) RUN_SLOPGATE_TEST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 - "$MANIFEST" "$BUNDLE_ROOT" "$ONLY" <<'PY'
from __future__ import annotations
import os, sys
from pathlib import Path
manifest_path = Path(sys.argv[1]); bundle_root = Path(sys.argv[2]).resolve(); only = sys.argv[3]
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
failures=0; checked=0
for e in parse(manifest_path):
    platform=e.get('platform','shared')
    if only != 'all' and platform != only: continue
    dest=Path(os.path.expandvars(os.path.expanduser(e['dest'])))
    checked += 1
    if not dest.is_symlink():
        print(f"FAIL not linked: {dest}"); failures += 1; continue
    target=dest.resolve(strict=False)
    try:
        target.relative_to(bundle_root)
    except ValueError:
        print(f"FAIL outside bundle: {dest} -> {target}"); failures += 1; continue
    if not target.exists():
        print(f"FAIL broken symlink: {dest} -> {target}"); failures += 1; continue
    print(f"OK {dest} -> {target}")
for root, dirs, files in os.walk(bundle_root):
    for name in dirs + files:
        p = Path(root) / name
        if p.is_symlink() and not p.resolve(strict=False).exists():
            print(f"FAIL broken symlink inside bundle: {p} -> {p.resolve(strict=False)}")
            failures += 1
if failures:
    raise SystemExit(f"verify failed: {failures} failure(s) across {checked} manifest link(s)")
print(f"verify ok: {checked} manifest link(s), only={only}")
PY

if [[ "$RUN_SLOPGATE_TEST" == "1" ]]; then
  command -v slopgate >/dev/null
  slopgate test
fi
