#!/usr/bin/env python3
"""Analyze quality violations from baselines.json.

Usage:
    python analyze_violations.py [--rule assertion_roulette] [--file path]
    python analyze_violations.py --summary
    python analyze_violations.py --actionable

Provides actionable insights for fixing violations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_baselines(path: Path) -> dict[str, list[str]]:
    """Load baselines.json."""
    if not path.exists():
        print(f"Baselines file not found: {path}")
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("rules", {})


def parse_violation(violation_id: str) -> dict[str, str]:
    """Parse a violation ID into components."""
    parts = violation_id.split("|")
    result = {"rule": parts[0], "path": parts[1] if len(parts) > 1 else ""}
    if len(parts) > 2:
        result["identifier"] = parts[2]
    if len(parts) > 3:
        result["detail"] = parts[3]
    return result


def print_summary(baselines: dict[str, list[str]]) -> None:
    """Print summary of all violations."""
    total = sum(len(v) for v in baselines.values())
    print(f"Total violations: {total}")
    print(f"Rules with violations: {len(baselines)}\n")

    print("Violations by rule:")
    print("-" * 50)
    for rule, violations in sorted(baselines.items(), key=lambda x: -len(x[1])):
        print(f"  {rule}: {len(violations)}")


def print_by_file(
    baselines: dict[str, list[str]], target_file: str | None = None
) -> None:
    """Print violations grouped by file."""
    by_file: dict[str, list[dict[str, str]]] = {}

    for rule, violations in baselines.items():
        for v in violations:
            parsed = parse_violation(v)
            filepath = parsed.get("path", "")

            if target_file and target_file not in filepath:
                continue

            if filepath not in by_file:
                by_file[filepath] = []
            by_file[filepath].append({**parsed, "rule": rule})

    for filepath, violations in sorted(by_file.items()):
        print(f"\n{filepath}:")
        print("-" * len(filepath))
        for v in sorted(violations, key=lambda x: x.get("identifier", "")):
            detail = f" ({v['detail']})" if v.get("detail") else ""
            print(f"  [{v['rule']}] {v.get('identifier', '')}{detail}")


def print_actionable(baselines: dict[str, list[str]]) -> None:
    """Print actionable recommendations by priority."""

    # Priority order based on ease of fixing
    priority_order = [
        # Quick fixes (< 5 min each)
        ("assertion_roulette", "Add assertion messages", "LOW"),
        ("raises_without_match", "Add match= to pytest.raises", "LOW"),
        ("sensitive_equality", "Replace str() comparison with attribute check", "LOW"),
        ("redundant_print", "Remove print statements", "LOW"),
        # Medium fixes (5-15 min each)
        ("thin_wrapper", "Inline or add meaningful logic", "MEDIUM"),
        ("sleepy_test", "Replace sleep with async patterns/mocks", "MEDIUM"),
        ("magic_number_test", "Extract to named constant", "MEDIUM"),
        ("long_test", "Split into focused tests", "MEDIUM"),
        ("eager_test", "Split into single-behavior tests", "MEDIUM"),
        # Larger refactors (15+ min each)
        ("long_method", "Extract helper functions", "HIGH"),
        ("deep_nesting", "Use early returns/guard clauses", "HIGH"),
        ("feature_envy", "Move method to accessed object", "HIGH"),
        ("god_class", "Extract to smaller focused classes", "HIGH"),
        ("module_size_soft", "Split into submodules", "HIGH"),
    ]

    print("ACTIONABLE VIOLATIONS BY PRIORITY")
    print("=" * 60)

    for rule, action, effort in priority_order:
        if rule not in baselines:
            continue

        count = len(baselines[rule])
        if count == 0:
            continue

        emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}[effort]
        print(f"\n{emoji} [{effort}] {rule}: {count} violations")
        print(f"   Action: {action}")

        # Show top 5 examples
        for v in baselines[rule][:5]:
            parsed = parse_violation(v)
            path = parsed.get("path", "").split("/")[-1]
            ident = parsed.get("identifier", "")
            print(f"   - {path}:{ident}")

        if count > 5:
            print(f"   ... and {count - 5} more")


def print_rule_details(baselines: dict[str, list[str]], rule: str) -> None:
    """Print detailed info for a specific rule."""
    if rule not in baselines:
        print(f"Rule '{rule}' not found in baselines.")
        print(f"Available rules: {', '.join(sorted(baselines.keys()))}")
        return

    violations = baselines[rule]
    print(f"Rule: {rule}")
    print(f"Count: {len(violations)}")
    print("-" * 50)

    # Group by file
    by_file: dict[str, list[dict[str, str]]] = {}
    for v in violations:
        parsed = parse_violation(v)
        path = parsed.get("path", "unknown")
        if path not in by_file:
            by_file[path] = []
        by_file[path].append(parsed)

    for filepath, file_violations in sorted(by_file.items()):
        print(f"\n{filepath}:")
        for v in sorted(file_violations, key=lambda x: x.get("identifier", "")):
            ident = v.get("identifier", "")
            detail = v.get("detail", "")
            if detail:
                print(f"  - {ident}: {detail}")
            else:
                print(f"  - {ident}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze quality violations")
    parser.add_argument(
        "--baselines",
        type=Path,
        default=Path("tests/quality/baselines.json"),
        help="Path to baselines.json",
    )
    parser.add_argument("--rule", type=str, help="Show details for specific rule")
    parser.add_argument("--file", type=str, help="Filter by file path")
    parser.add_argument("--summary", action="store_true", help="Show summary only")
    parser.add_argument(
        "--actionable",
        action="store_true",
        help="Show actionable recommendations by priority",
    )
    args = parser.parse_args()

    baselines = load_baselines(args.baselines)
    if not baselines:
        return

    if args.summary:
        print_summary(baselines)
    elif args.actionable:
        print_actionable(baselines)
    elif args.rule:
        print_rule_details(baselines, args.rule)
    elif args.file:
        print_by_file(baselines, args.file)
    else:
        print_summary(baselines)
        print("\nUse --actionable for prioritized recommendations")
        print("Use --rule <name> for details on a specific rule")
        print("Use --file <path> to filter by file")


if __name__ == "__main__":
    main()
