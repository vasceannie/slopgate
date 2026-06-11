#!/usr/bin/env python3
"""Analyze existing tests for extension opportunities.

Searches for pytest test files and identifies:
- Tests that can be extended with parametrization
- Similar test patterns that should be consolidated
- Tests missing assertion messages
- Tests with loops/conditionals (anti-patterns)
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestAnalysis:
    """Analysis result for a single test function."""

    file_path: str
    test_name: str
    line_number: int
    issues: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    has_parametrize: bool = False
    assertion_count: int = 0
    assertions_without_msg: int = 0
    has_loop: bool = False
    has_conditional: bool = False


class TestVisitor(ast.NodeVisitor):
    """AST visitor to analyze test function bodies."""

    def __init__(self) -> None:
        self.assertions: list[tuple[int, bool]] = []  # (line, has_message)
        self.has_loop = False
        self.has_conditional = False
        self.magic_values: list[tuple[int, str]] = []
        self.similar_assertions: list[str] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        has_msg = node.msg is not None
        self.assertions.append((node.lineno, has_msg))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check for pytest.raises without match=
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "raises":
                has_match = any(kw.arg == "match" for kw in node.keywords)
                if not has_match:
                    self.assertions.append((node.lineno, False))
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.has_loop = True
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.has_loop = True
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.has_conditional = True
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # Detect magic values (numbers > 1, non-empty strings not in common patterns)
        if isinstance(node.value, int) and node.value > 1:
            self.magic_values.append((node.lineno, str(node.value)))
        elif isinstance(node.value, float):
            self.magic_values.append((node.lineno, str(node.value)))
        self.generic_visit(node)


def find_test_files(directory: Path, pattern: str = "test_*.py") -> list[Path]:
    """Find all test files using ripgrep for speed."""
    try:
        result = subprocess.run(
            ["rg", "--files", "-g", pattern, str(directory)],
            capture_output=True,
            text=True,
            check=True,
        )
        return [Path(p) for p in result.stdout.strip().split("\n") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to glob if rg not available
        return list(directory.rglob(pattern))


def analyze_test_function(
    func: ast.FunctionDef, file_path: Path, decorators: list[str]
) -> TestAnalysis:
    """Analyze a single test function."""
    analysis = TestAnalysis(
        file_path=str(file_path),
        test_name=func.name,
        line_number=func.lineno,
    )

    # Check for existing parametrize
    analysis.has_parametrize = any("parametrize" in d for d in decorators)

    # Visit function body
    visitor = TestVisitor()
    for node in ast.walk(func):
        visitor.visit(node)

    analysis.assertion_count = len(visitor.assertions)
    analysis.assertions_without_msg = sum(1 for _, has_msg in visitor.assertions if not has_msg)
    analysis.has_loop = visitor.has_loop
    analysis.has_conditional = visitor.has_conditional

    # Record issues
    if visitor.has_loop:
        analysis.issues.append("Contains loop - use parametrize instead")
    if visitor.has_conditional:
        analysis.issues.append("Contains conditional - split into separate tests or parametrize")
    if analysis.assertions_without_msg > 0:
        analysis.issues.append(
            f"{analysis.assertions_without_msg} assertion(s) missing descriptive message"
        )
    if visitor.magic_values:
        values = ", ".join(f"line {ln}: {v}" for ln, v in visitor.magic_values[:3])
        analysis.issues.append(f"Magic values detected: {values}")

    # Record opportunities
    if not analysis.has_parametrize and analysis.assertion_count > 2:
        analysis.opportunities.append("Consider parametrizing multiple assertions")
    if visitor.magic_values:
        analysis.opportunities.append("Extract magic values to constants or fixtures")

    return analysis


def get_decorator_names(decorators: list[ast.expr]) -> list[str]:
    """Extract decorator names as strings."""
    names = []
    for dec in decorators:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Attribute):
                names.append(dec.func.attr)
            elif isinstance(dec.func, ast.Name):
                names.append(dec.func.id)
    return names


def analyze_file(file_path: Path) -> list[TestAnalysis]:
    """Analyze all test functions in a file."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError) as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return []

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            decorators = get_decorator_names(node.decorator_list)
            analysis = analyze_test_function(node, file_path, decorators)
            results.append(analysis)

    return results


def find_similar_tests(analyses: list[TestAnalysis]) -> dict[str, list[str]]:
    """Find tests with similar names that might be consolidated."""
    # Group by prefix (test_<function>_)
    groups: dict[str, list[str]] = {}
    for analysis in analyses:
        # Extract base name pattern
        match = re.match(r"test_(\w+?)_", analysis.test_name)
        if match:
            base = match.group(1)
            key = f"test_{base}_*"
            if key not in groups:
                groups[key] = []
            groups[key].append(f"{analysis.file_path}:{analysis.test_name}")

    # Filter to groups with multiple tests
    return {k: v for k, v in groups.items() if len(v) > 2}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze tests for extension opportunities")
    parser.add_argument("directory", type=Path, help="Directory to search for tests")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--issues-only", action="store_true", help="Only show tests with issues")
    args = parser.parse_args()

    test_files = find_test_files(args.directory)
    all_analyses: list[TestAnalysis] = []

    for test_file in test_files:
        analyses = analyze_file(test_file)
        all_analyses.extend(analyses)

    if args.issues_only:
        all_analyses = [a for a in all_analyses if a.issues]

    similar_groups = find_similar_tests(all_analyses)

    if args.json:
        output = {
            "analyses": [
                {
                    "file": a.file_path,
                    "test": a.test_name,
                    "line": a.line_number,
                    "issues": a.issues,
                    "opportunities": a.opportunities,
                    "has_parametrize": a.has_parametrize,
                }
                for a in all_analyses
            ],
            "similar_test_groups": similar_groups,
            "summary": {
                "total_tests": len(all_analyses),
                "tests_with_issues": sum(1 for a in all_analyses if a.issues),
                "tests_with_loops": sum(1 for a in all_analyses if a.has_loop),
                "tests_with_conditionals": sum(1 for a in all_analyses if a.has_conditional),
                "parametrized_tests": sum(1 for a in all_analyses if a.has_parametrize),
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n=== Test Analysis Summary ===")
        print(f"Total tests found: {len(all_analyses)}")
        print(f"Tests with issues: {sum(1 for a in all_analyses if a.issues)}")
        print(f"Already parametrized: {sum(1 for a in all_analyses if a.has_parametrize)}")

        if similar_groups:
            print(f"\n=== Similar Test Groups (consolidation candidates) ===")
            for pattern, tests in similar_groups.items():
                print(f"\n{pattern} ({len(tests)} tests):")
                for t in tests[:5]:
                    print(f"  - {t}")
                if len(tests) > 5:
                    print(f"  ... and {len(tests) - 5} more")

        issues_found = [a for a in all_analyses if a.issues]
        if issues_found:
            print(f"\n=== Tests with Issues ===")
            for analysis in issues_found[:20]:
                print(f"\n{analysis.file_path}:{analysis.line_number} - {analysis.test_name}")
                for issue in analysis.issues:
                    print(f"  - {issue}")
                for opp in analysis.opportunities:
                    print(f"  + {opp}")


if __name__ == "__main__":
    main()
