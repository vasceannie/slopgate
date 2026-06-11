#!/usr/bin/env python3
"""Discover and analyze pytest fixtures across the project.

Searches for fixtures in conftest.py files at all directory levels,
analyzes scope, dependencies, and reuse opportunities.
"""

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FixtureInfo:
    """Information about a discovered fixture."""

    name: str
    file_path: str
    line_number: int
    scope: str
    autouse: bool
    params: list[str]
    dependencies: list[str]
    docstring: str | None
    return_type: str | None


@dataclass
class FixtureUsage:
    """Track where a fixture is used."""

    fixture_name: str
    used_in_files: list[str] = field(default_factory=list)
    used_in_tests: list[str] = field(default_factory=list)


def find_conftest_files(directory: Path) -> list[Path]:
    """Find all conftest.py files."""
    try:
        result = subprocess.run(
            ["rg", "--files", "-g", "conftest.py", str(directory)],
            capture_output=True,
            text=True,
            check=True,
        )
        return [Path(p) for p in result.stdout.strip().split("\n") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return list(directory.rglob("conftest.py"))


def find_test_files(directory: Path) -> list[Path]:
    """Find all test files."""
    try:
        result = subprocess.run(
            ["rg", "--files", "-g", "test_*.py", str(directory)],
            capture_output=True,
            text=True,
            check=True,
        )
        return [Path(p) for p in result.stdout.strip().split("\n") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return list(directory.rglob("test_*.py"))


def extract_fixture_info(func: ast.FunctionDef, file_path: Path) -> FixtureInfo | None:
    """Extract fixture information from a decorated function."""
    scope = "function"
    autouse = False
    params: list[str] = []

    # Check for @pytest.fixture decorator
    is_fixture = False
    for decorator in func.decorator_list:
        dec_name = None
        if isinstance(decorator, ast.Name):
            dec_name = decorator.id
        elif isinstance(decorator, ast.Attribute):
            dec_name = decorator.attr
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                dec_name = decorator.func.attr
            elif isinstance(decorator.func, ast.Name):
                dec_name = decorator.func.id

            # Extract fixture arguments
            if dec_name == "fixture":
                for kw in decorator.keywords:
                    if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                        scope = str(kw.value.value)
                    elif kw.arg == "autouse" and isinstance(kw.value, ast.Constant):
                        autouse = bool(kw.value.value)
                    elif kw.arg == "params" and isinstance(kw.value, ast.List):
                        params = [ast.dump(e) for e in kw.value.elts]

        if dec_name == "fixture":
            is_fixture = True

    if not is_fixture:
        return None

    # Extract dependencies (function arguments except 'request')
    dependencies = [
        arg.arg for arg in func.args.args if arg.arg not in ("self", "request")
    ]

    # Extract docstring
    docstring = ast.get_docstring(func)

    # Extract return type annotation
    return_type = None
    if func.returns:
        return_type = ast.unparse(func.returns)

    return FixtureInfo(
        name=func.name,
        file_path=str(file_path),
        line_number=func.lineno,
        scope=scope,
        autouse=autouse,
        params=params,
        dependencies=dependencies,
        docstring=docstring,
        return_type=return_type,
    )


def analyze_conftest(file_path: Path) -> list[FixtureInfo]:
    """Analyze a conftest.py file for fixtures."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError) as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        return []

    fixtures = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            info = extract_fixture_info(node, file_path)
            if info:
                fixtures.append(info)

    return fixtures


def find_fixture_usage(test_file: Path, fixture_names: set[str]) -> dict[str, list[str]]:
    """Find which fixtures are used in a test file."""
    try:
        source = test_file.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return {}

    usage: dict[str, list[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            for arg in node.args.args:
                if arg.arg in fixture_names:
                    if arg.arg not in usage:
                        usage[arg.arg] = []
                    usage[arg.arg].append(f"{test_file}:{node.name}")

    return usage


def find_duplicate_fixtures(fixtures: list[FixtureInfo]) -> dict[str, list[str]]:
    """Find fixtures with same name defined in multiple conftest files."""
    name_locations: dict[str, list[str]] = {}
    for fix in fixtures:
        if fix.name not in name_locations:
            name_locations[fix.name] = []
        name_locations[fix.name].append(f"{fix.file_path}:{fix.line_number}")

    return {name: locs for name, locs in name_locations.items() if len(locs) > 1}


def suggest_scope_improvements(
    fixtures: list[FixtureInfo], usage: dict[str, FixtureUsage]
) -> list[str]:
    """Suggest scope improvements based on usage patterns."""
    suggestions = []

    for fix in fixtures:
        if fix.name in usage:
            use_count = len(usage[fix.name].used_in_tests)
            file_count = len(set(usage[fix.name].used_in_files))

            # Suggest module scope if used in many tests in same file
            if fix.scope == "function" and use_count > 5 and file_count == 1:
                suggestions.append(
                    f"{fix.name}: Consider 'module' scope (used {use_count} times in 1 file)"
                )

            # Suggest session scope if used across many files
            if fix.scope in ("function", "module") and file_count > 3:
                suggestions.append(
                    f"{fix.name}: Consider 'session' scope (used in {file_count} files)"
                )

    return suggestions


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and analyze pytest fixtures")
    parser.add_argument("directory", type=Path, help="Directory to search")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--with-usage", action="store_true", help="Include usage analysis")
    args = parser.parse_args()

    conftest_files = find_conftest_files(args.directory)
    all_fixtures: list[FixtureInfo] = []

    for conftest in conftest_files:
        fixtures = analyze_conftest(conftest)
        all_fixtures.extend(fixtures)

    fixture_names = {f.name for f in all_fixtures}
    duplicates = find_duplicate_fixtures(all_fixtures)

    usage_map: dict[str, FixtureUsage] = {}
    if args.with_usage:
        test_files = find_test_files(args.directory)
        for test_file in test_files:
            usage = find_fixture_usage(test_file, fixture_names)
            for name, tests in usage.items():
                if name not in usage_map:
                    usage_map[name] = FixtureUsage(fixture_name=name)
                usage_map[name].used_in_files.append(str(test_file))
                usage_map[name].used_in_tests.extend(tests)

    if args.json:
        output: dict[str, object] = {
            "fixtures": [
                {
                    "name": f.name,
                    "file": f.file_path,
                    "line": f.line_number,
                    "scope": f.scope,
                    "autouse": f.autouse,
                    "dependencies": f.dependencies,
                    "return_type": f.return_type,
                    "docstring": f.docstring,
                }
                for f in all_fixtures
            ],
            "duplicates": duplicates,
            "by_scope": {
                scope: [f.name for f in all_fixtures if f.scope == scope]
                for scope in ["function", "class", "module", "session"]
            },
        }
        if args.with_usage:
            output["usage"] = {
                name: {
                    "files": list(set(u.used_in_files)),
                    "test_count": len(u.used_in_tests),
                }
                for name, u in usage_map.items()
            }
            output["scope_suggestions"] = suggest_scope_improvements(all_fixtures, usage_map)

        print(json.dumps(output, indent=2))
    else:
        print(f"\n=== Fixture Discovery Summary ===")
        print(f"Conftest files found: {len(conftest_files)}")
        print(f"Total fixtures: {len(all_fixtures)}")

        # Group by scope
        by_scope = {}
        for f in all_fixtures:
            if f.scope not in by_scope:
                by_scope[f.scope] = []
            by_scope[f.scope].append(f)

        print(f"\n=== Fixtures by Scope ===")
        for scope in ["function", "class", "module", "session"]:
            if scope in by_scope:
                print(f"\n{scope.upper()} scope ({len(by_scope[scope])}):")
                for f in by_scope[scope][:10]:
                    deps = f", deps: {f.dependencies}" if f.dependencies else ""
                    print(f"  - {f.name} ({f.file_path}:{f.line_number}){deps}")
                if len(by_scope[scope]) > 10:
                    print(f"  ... and {len(by_scope[scope]) - 10} more")

        if duplicates:
            print(f"\n=== Duplicate Fixture Names (potential conflicts) ===")
            for name, locations in duplicates.items():
                print(f"\n{name}:")
                for loc in locations:
                    print(f"  - {loc}")

        if args.with_usage:
            suggestions = suggest_scope_improvements(all_fixtures, usage_map)
            if suggestions:
                print(f"\n=== Scope Optimization Suggestions ===")
                for sug in suggestions:
                    print(f"  - {sug}")

            # Show unused fixtures
            unused = [f for f in all_fixtures if f.name not in usage_map and not f.autouse]
            if unused:
                print(f"\n=== Potentially Unused Fixtures ===")
                for f in unused[:10]:
                    print(f"  - {f.name} ({f.file_path})")


if __name__ == "__main__":
    main()
