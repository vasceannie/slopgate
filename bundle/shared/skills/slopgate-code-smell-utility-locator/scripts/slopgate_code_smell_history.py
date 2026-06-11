#!/usr/bin/env python3
"""Summarize repeated slopgate code-smell hook activations without dumping raw logs."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, cast

CODE_SMELL_RULES = {
    "PY-CODE-008",
    "PY-CODE-009",
    "PY-CODE-011",
    "PY-CODE-012",
    "PY-CODE-013",
    "PY-CODE-014",
    "PY-CODE-018",
    "QUALITY-LINT-001",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", default="/home/trav/.config/slopgate/logs", help="slopgate log directory")
    parser.add_argument("--threshold", type=int, default=2, help="Minimum same rule/path count to report")
    parser.add_argument("--limit", type=int, default=40, help="Maximum rows to print")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def iter_jsonl(path: Path) -> Iterable[dict[str, object]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def pick_path(record: dict[str, object]) -> str:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        metadata_dict = cast(dict[str, object], metadata)
        value = metadata_dict.get("path") or metadata_dict.get("file")
        if isinstance(value, str):
            return value
        hits = metadata_dict.get("hits")
        if isinstance(hits, list) and hits:
            first = hits[0]
            if isinstance(first, dict):
                first_dict = cast(dict[str, object], first)
                candidate = first_dict.get("path") or first_dict.get("file")
                if isinstance(candidate, str):
                    return candidate
    for key in ("path", "file", "file_path", "target_path"):
        value = record.get(key)
        if isinstance(value, str):
            return value
    return "<unknown>"


def summarize(logs: Path, threshold: int) -> list[dict[str, object]]:
    counts: Counter[tuple[str, str]] = Counter()
    decisions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    sources = [logs / "rules.jsonl", logs / "results.jsonl"]
    for source in sources:
        for record in iter_jsonl(source):
            rule_id = record.get("rule_id") or record.get("rule") or record.get("id")
            if not isinstance(rule_id, str) or rule_id not in CODE_SMELL_RULES:
                continue
            path = pick_path(record)
            key = (rule_id, path)
            counts[key] += 1
            decision = record.get("decision") or record.get("outcome") or record.get("severity") or "unknown"
            if isinstance(decision, str):
                decisions[key][decision] += 1
    rows: list[dict[str, object]] = []
    for (rule_id, path), count in counts.most_common():
        if count < threshold:
            continue
        rows.append({
            "rule_id": rule_id,
            "path": path,
            "count": count,
            "decisions": dict(decisions[(rule_id, path)]),
            "recommended_skill": "code-smell-utility-locator",
        })
    return rows


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    rows = summarize(Path(args.logs).expanduser(), args.threshold)[: max(args.limit, 0)]
    if args.format == "json":
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    print(f"repeated slopgate code-smell activations: {len(rows)} row(s)")
    for row in rows:
        print(f"- {row['rule_id']} {row['path']} count={row['count']} decisions={row['decisions']}")
        print("  next: load code-smell-utility-locator; run utility_inventory.py and code_smell_radar.py before retrying")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
