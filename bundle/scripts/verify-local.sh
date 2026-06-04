#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$BUNDLE_ROOT/manifest.yaml"
ONLY="all"
RUN_SLOPGATE_TEST=0
STRICT=0
VERBOSE=0

usage() {
  cat <<'USAGE'
Usage: verify-local.sh [--only claude|opencode|codex|cursor] [--strict] [--verbose] [--slopgate-test]

Default mode is migration-safe and concise: exact bundle-owned symlinks are
verified, while legacy real paths and old non-bundle symlinks are counted as
WARNs and do not fail the check. Use --verbose to print each WARN. Use --strict
to require every manifest destination to be an exact symlink to its manifest
source.
USAGE
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) shift; ONLY="${1:-}"; case "$ONLY" in claude|opencode|codex|cursor) ;; *) echo "invalid --only: $ONLY" >&2; exit 2 ;; esac ;;
    --strict) STRICT=1 ;;
    --verbose) VERBOSE=1 ;;
    --slopgate-test) RUN_SLOPGATE_TEST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python3 - "$MANIFEST" "$BUNDLE_ROOT" "$ONLY" "$STRICT" "$VERBOSE" <<'PY'
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

manifest_path = Path(sys.argv[1])
bundle_root = Path(sys.argv[2]).resolve()
only = sys.argv[3]
strict = sys.argv[4] == "1"
verbose = sys.argv[5] == "1"


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


def record_warning(kind: str, message: str) -> None:
    warning_counts[kind] += 1
    if verbose or strict:
        prefix = "FAIL" if strict else "WARN"
        print(f"{prefix} {message}")


failures = 0
checked = 0
ok = 0
warning_counts: Counter[str] = Counter()
for entry in parse(manifest_path):
    platform = entry.get("platform", "shared")
    if only != "all" and platform != only:
        continue
    checked += 1
    src_value = entry.get("src")
    dest_value = entry.get("dest")
    if not src_value or not dest_value:
        print(f"FAIL manifest entry missing src/dest: {entry}")
        failures += 1
        continue

    expected = (bundle_root / src_value).resolve(strict=False)
    if not is_relative_to(expected, bundle_root):
        print(f"FAIL source escapes bundle: {src_value} -> {expected}")
        failures += 1
        continue
    if not expected.exists():
        print(f"FAIL missing source: {src_value} -> {expected}")
        failures += 1
        continue

    dest = Path(os.path.expandvars(os.path.expanduser(dest_value)))
    if dest.is_symlink():
        target = dest.resolve(strict=False)
        if target == expected:
            print(f"OK {dest} -> {target}")
            ok += 1
            continue
        if not target.exists():
            print(f"FAIL broken symlink: {dest} -> {target}")
            failures += 1
            continue
        if is_relative_to(target, bundle_root):
            print(f"FAIL bundle symlink target mismatch: {dest} -> {target}; expected {expected}")
            failures += 1
            continue
        record_warning("non_bundle_symlink", f"existing non-bundle symlink: {dest} -> {target}; expected {expected}")
        if strict:
            failures += 1
        continue

    if dest.exists():
        record_warning("real_path", f"existing real path: {dest}; expected symlink -> {expected}")
    else:
        record_warning("missing", f"missing live path: {dest}; expected symlink -> {expected}")
    if strict:
        failures += 1

for root, dirs, files in os.walk(bundle_root):
    for name in dirs + files:
        path = Path(root) / name
        if path.is_symlink() and not path.resolve(strict=False).exists():
            print(f"FAIL broken symlink inside bundle: {path} -> {path.resolve(strict=False)}")
            failures += 1

warning_total = sum(warning_counts.values())
warning_summary = ", ".join(f"{key}={warning_counts[key]}" for key in sorted(warning_counts)) or "none"
if failures:
    raise SystemExit(
        f"verify failed: failures={failures}, ok={ok}, warnings={warning_total} ({warning_summary}), checked={checked}, only={only}, strict={strict}"
    )
print(f"verify ok: ok={ok}, warnings={warning_total} ({warning_summary}), checked={checked}, only={only}, strict={strict}")
PY

if [[ "$RUN_SLOPGATE_TEST" == "1" ]]; then
  command -v slopgate >/dev/null
  slopgate test
fi
