#!/usr/bin/env python3
"""Suggest renames for duplicate test names.

Usage:
    python suggest_test_renames.py [--path tests/]

Finds tests with identical names and suggests unique renames.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path


def find_test_files(root: Path) -> list[Path]:
    """Find test files."""
    files: list[Path] = []
    for py_file in root.rglob("test_*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        if "quality" in py_file.parts:
            continue
        files.append(py_file)
    return files


def extract_test_names(file_path: Path) -> list[tuple[str, int]]:
    """Extract test function names and line numbers."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    tests: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                tests.append((node.name, node.lineno))
    return tests


def suggest_rename(
    name: str,
    file_path: Path,
    existing_names: set[str],
) -> str:
    """Suggest a unique rename based on file context."""
    # Extract meaningful suffix from file name
    file_stem = file_path.stem.replace("test_", "")

    # Try adding file context
    suggestion = f"{name}_{file_stem}"
    if suggestion not in existing_names:
        return suggestion

    # Try with parent directory
    parent = file_path.parent.name
    suggestion = f"{name}_{parent}_{file_stem}"
    if suggestion not in existing_names:
        return suggestion

    # Fallback to numbered suffix
    counter = 2
    base = f"{name}_{file_stem}"
    while f"{base}_{counter}" in existing_names:
        counter += 1
    return f"{base}_{counter}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suggest renames for duplicate test names"
    )
    parser.add_argument(
        "--path", type=Path, default=Path("tests"), help="Root path to search"
    )
    parser.add_argument(
        "--output-script", action="store_true", help="Output as sed/rename script"
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Path not found: {args.path}")
        return

    # Collect all test names
    test_locations: dict[str, list[tuple[Path, int]]] = defaultdict(list)

    for f in find_test_files(args.path):
        for name, lineno in extract_test_names(f):
            test_locations[name].append((f, lineno))

    # Find duplicates
    duplicates = {name: locs for name, locs in test_locations.items() if len(locs) > 1}

    if not duplicates:
        print("No duplicate test names found.")
        return

    print(f"Found {len(duplicates)} duplicate test name(s)\n")

    # Collect all existing names to avoid conflicts
    all_names = set(test_locations.keys())

    # Generate suggestions
    renames: list[tuple[Path, int, str, str]] = []

    for name, locations in sorted(duplicates.items()):
        print(f"Duplicate: {name} ({len(locations)} occurrences)")

        # Keep first occurrence, rename others
        for i, (file_path, lineno) in enumerate(locations):
            if i == 0:
                print(f"  KEEP: {file_path}:{lineno}")
            else:
                new_name = suggest_rename(name, file_path, all_names)
                all_names.add(new_name)
                renames.append((file_path, lineno, name, new_name))
                print(f"  RENAME: {file_path}:{lineno}")
                print(f"          {name} -> {new_name}")
        print()

    if args.output_script and renames:
        print("\n# Rename script (review before running!):")
        print("# " + "=" * 50)
        for file_path, lineno, old_name, new_name in renames:
            # sed command to rename in place
            print(f"sed -i 's/def {old_name}/def {new_name}/g' {file_path}")


if __name__ == "__main__":
    main()
