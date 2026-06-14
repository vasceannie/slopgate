#!/usr/bin/env python3
"""Parse lint outputs from .hygeine/ into unified JSON format for orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LintIssue:
    """Unified lint issue representation."""

    file: str
    line: int
    column: int
    severity: str  # "error" | "warning" | "info"
    code: str  # e.g., "unbound-name", "noExplicitAny"
    message: str
    source: str  # "pyrefly" | "biome" | "clippy" | "tsc"
    category: str = ""  # Grouping category
    fixable: bool = False


@dataclass
class UnifiedOutput:
    """Unified output containing all parsed issues."""

    generated_at: str
    total_errors: int = 0
    total_warnings: int = 0
    issues: list[LintIssue] = field(default_factory=list)
    by_file: dict[str, list[int]] = field(default_factory=dict)  # file -> issue indices
    by_category: dict[str, list[int]] = field(
        default_factory=dict
    )  # category -> issue indices


def parse_pyrefly(content: str) -> list[LintIssue]:
    """Parse pyrefly JSON output format (pyrefly check --output-format json)."""
    issues: list[LintIssue] = []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return issues

    for err in data.get("errors", []):
        issues.append(
            LintIssue(
                file=err.get("path", "unknown"),
                line=err.get("line", 1),
                column=err.get("column", 1),
                severity=err.get("severity", "error"),
                code=err.get("name", "unknown"),
                message=err.get("concise_description", err.get("description", "")),
                source="pyrefly",
                category=categorize_python_issue(err.get("name", "")),
            )
        )

    return issues


def parse_biome_json(content: str) -> list[LintIssue]:
    """Parse Biome JSON output format."""
    issues: list[LintIssue] = []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return issues

    diagnostics = data if isinstance(data, list) else data.get("diagnostics", [])

    for diag in diagnostics:
        location = diag.get("location", {})
        path = location.get("path", {}).get("file", "unknown")
        span = location.get("span", [0, 0])

        # Biome uses byte offsets, approximate line/col
        line = diag.get("line", 1)
        col = diag.get("column", span[0] if span else 1)

        severity = diag.get("severity", "error").lower()
        if severity not in ("error", "warning", "info"):
            severity = "warning"

        issues.append(
            LintIssue(
                file=path,
                line=line,
                column=col,
                severity=severity,
                code=diag.get("category", "unknown"),
                message=diag.get("message", ""),
                source="biome",
                category=categorize_ts_issue(diag.get("category", "")),
                fixable=diag.get("fixable", False),
            )
        )

    return issues


def parse_clippy_json(content: str) -> list[LintIssue]:
    """Parse Clippy JSON output format (cargo clippy --message-format=json)."""
    issues: list[LintIssue] = []

    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("reason") != "compiler-message":
            continue

        msg = data.get("message", {})
        level = msg.get("level", "warning")
        if level not in ("error", "warning"):
            continue

        spans = msg.get("spans", [])
        if not spans:
            continue

        primary = next((s for s in spans if s.get("is_primary")), spans[0])

        issues.append(
            LintIssue(
                file=primary.get("file_name", "unknown"),
                line=primary.get("line_start", 1),
                column=primary.get("column_start", 1),
                severity=level,
                code=msg.get("code", {}).get("code", "unknown")
                if msg.get("code")
                else "unknown",
                message=msg.get("message", ""),
                source="clippy",
                category=categorize_rust_issue(
                    msg.get("code", {}).get("code", "") if msg.get("code") else ""
                ),
            )
        )

    return issues


def categorize_python_issue(code: str) -> str:
    """Categorize Python lint codes into groups."""
    type_issues = {
        "unbound-name",
        "missing-attribute",
        "bad-argument-type",
        "not-iterable",
        "type-mismatch",
    }
    import_issues = {"untyped-import", "import-error", "missing-import"}
    none_safety = {"none-return", "optional-member-access", "possibly-undefined"}

    if code in type_issues:
        return "type-safety"
    if code in import_issues:
        return "imports"
    if code in none_safety:
        return "none-safety"
    return "general"


def categorize_ts_issue(code: str) -> str:
    """Categorize TypeScript lint codes into groups."""
    if "Any" in code or "any" in code:
        return "type-safety"
    if "unused" in code.lower():
        return "dead-code"
    if "import" in code.lower():
        return "imports"
    return "general"


def categorize_rust_issue(code: str) -> str:
    """Categorize Rust lint codes into groups."""
    if "unwrap" in code or "expect" in code:
        return "error-handling"
    if "dead_code" in code or "unused" in code:
        return "dead-code"
    return "general"


def build_indices(
    issues: list[LintIssue],
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Build file and category indices for issues."""
    by_file: dict[str, list[int]] = {}
    by_category: dict[str, list[int]] = {}

    for i, issue in enumerate(issues):
        by_file.setdefault(issue.file, []).append(i)
        by_category.setdefault(issue.category or "general", []).append(i)

    return by_file, by_category


def parse_directory(hygiene_dir: Path) -> UnifiedOutput:
    """Parse all lint outputs in the hygiene directory."""
    all_issues: list[LintIssue] = []

    # Parse pyrefly
    pyrefly_path = hygiene_dir / "pyrefly.json"
    if pyrefly_path.exists():
        all_issues.extend(parse_pyrefly(pyrefly_path.read_text()))

    # Parse biome
    biome_path = hygiene_dir / "biome.json"
    if biome_path.exists():
        all_issues.extend(parse_biome_json(biome_path.read_text()))

    # Parse clippy
    clippy_path = hygiene_dir / "clippy.json"
    if clippy_path.exists():
        all_issues.extend(parse_clippy_json(clippy_path.read_text()))

    by_file, by_category = build_indices(all_issues)

    return UnifiedOutput(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_errors=sum(1 for i in all_issues if i.severity == "error"),
        total_warnings=sum(1 for i in all_issues if i.severity == "warning"),
        issues=all_issues,
        by_file=by_file,
        by_category=by_category,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parse lint outputs into unified format"
    )
    parser.add_argument("hygiene_dir", type=Path, help="Path to .hygeine/ directory")
    parser.add_argument("--output", "-o", type=Path, help="Output JSON file path")
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )

    args = parser.parse_args()

    if not args.hygiene_dir.is_dir():
        print(f"Error: {args.hygiene_dir} is not a directory", file=sys.stderr)
        return 1

    output = parse_directory(args.hygiene_dir)

    # Convert to JSON-serializable format
    result = {
        "generated_at": output.generated_at,
        "total_errors": output.total_errors,
        "total_warnings": output.total_warnings,
        "issues": [asdict(i) for i in output.issues],
        "by_file": output.by_file,
        "by_category": output.by_category,
    }

    json_str = json.dumps(result, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(json_str)
        print(f"Wrote {len(output.issues)} issues to {args.output}")
    else:
        print(json_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
