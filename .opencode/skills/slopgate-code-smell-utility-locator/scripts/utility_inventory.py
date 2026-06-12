#!/usr/bin/env python3
"""Inventory shared utility locations/signatures before creating more helpers."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from _code_smell_scan import Item, records_to_json, scan

CATEGORIES = (
    "helpers",
    "builders",
    "factories",
    "constants",
    "configs",
    "dataclasses",
    "facades",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", nargs="?", default=".", help="Repository root or subdirectory to scan"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--category",
        action="append",
        choices=CATEGORIES,
        help="Limit to one or more categories",
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="Maximum records to print"
    )
    parser.add_argument(
        "--no-tests", action="store_true", help="Skip tests/spec directories"
    )
    parser.add_argument(
        "--grep", help="Case-insensitive substring filter over name/signature/path"
    )
    return parser.parse_args(argv)


def filter_items(items: list[Item], args: argparse.Namespace) -> list[Item]:
    wanted = set(args.category or CATEGORIES)
    filtered = [item for item in items if item.category in wanted]
    if args.grep:
        needle = args.grep.lower()
        filtered = [
            item
            for item in filtered
            if needle in item.name.lower()
            or needle in item.signature.lower()
            or needle in item.path.lower()
            or needle in item.reason.lower()
        ]
    return filtered[: max(args.limit, 0)]


def print_text(items: list[Item], total_before_limit: int) -> None:
    by_category: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_category[item.category].append(item)
    print(
        f"shared utility inventory: showing {len(items)} of {total_before_limit} matches"
    )
    for category in CATEGORIES:
        rows = by_category.get(category, [])
        if not rows:
            continue
        print(f"\n[{category}] {len(rows)}")
        for item in rows:
            print(f"- {item.path}:{item.line} {item.signature}")
            print(f"  reason: {item.reason}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2
    items, _funcs = scan(root, include_tests=not args.no_tests)
    filtered_all = filter_items(
        items, argparse.Namespace(**{**vars(args), "limit": 10**9})
    )
    limited = filtered_all[: max(args.limit, 0)]
    if args.format == "json":
        print(records_to_json(limited))
    else:
        print_text(limited, len(filtered_all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
