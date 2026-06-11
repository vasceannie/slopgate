#!/usr/bin/env python3
"""Search for existing constants in the codebase.

Usage:
    python find_constants.py <value>
    python find_constants.py --pattern "timeout|interval"
    python find_constants.py --numeric 86400

Helps find existing constants before creating new ones.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


def find_python_files(root: Path) -> list[Path]:
    """Find Python source files."""
    excluded = {"*_pb2.py", "*_pb2_grpc.py"}
    files: list[Path] = []

    for py_file in root.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        if any(py_file.match(p) for p in excluded):
            continue
        files.append(py_file)

    return files


def find_constant_assignments(
    file_path: Path,
) -> list[tuple[str, object, int, str]]:
    """Find CONSTANT_NAME = value assignments."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    constants: list[tuple[str, object, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Check if it looks like a constant (UPPER_CASE)
                    if target.id.isupper() or target.id.startswith("_") and target.id[1:].isupper():
                        if isinstance(node.value, ast.Constant):
                            constants.append((
                                target.id,
                                node.value.value,
                                node.lineno,
                                str(file_path),
                            ))

    return constants


def find_final_annotations(
    file_path: Path,
) -> list[tuple[str, object | None, int, str]]:
    """Find NAME: Final[...] = value annotations."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    finals: list[tuple[str, object | None, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            # Check for Final annotation
            is_final = False
            if isinstance(node.annotation, ast.Subscript):
                if isinstance(node.annotation.value, ast.Name):
                    is_final = node.annotation.value.id == "Final"
                elif isinstance(node.annotation.value, ast.Attribute):
                    is_final = node.annotation.value.attr == "Final"
            elif isinstance(node.annotation, ast.Name):
                is_final = node.annotation.id == "Final"

            if is_final:
                value = None
                if isinstance(node.value, ast.Constant):
                    value = node.value.value
                finals.append((
                    node.target.id,
                    value,
                    node.lineno,
                    str(file_path),
                ))

    return finals


def search_constants(
    root: Path,
    value: str | None = None,
    pattern: str | None = None,
    numeric: int | float | None = None,
) -> None:
    """Search for constants matching criteria."""
    files = find_python_files(root)

    all_constants: list[tuple[str, object, int, str]] = []

    for f in files:
        all_constants.extend(find_constant_assignments(f))
        all_constants.extend(find_final_annotations(f))

    print(f"Found {len(all_constants)} constants in {len(files)} files\n")

    matches: list[tuple[str, object, int, str]] = []

    for name, const_value, lineno, filepath in all_constants:
        if value is not None:
            # Exact string match on name or value
            if value.lower() in name.lower() or str(const_value).lower() == value.lower():
                matches.append((name, const_value, lineno, filepath))
        elif pattern is not None:
            # Regex match on name
            if re.search(pattern, name, re.IGNORECASE):
                matches.append((name, const_value, lineno, filepath))
        elif numeric is not None:
            # Numeric value match
            if const_value == numeric:
                matches.append((name, const_value, lineno, filepath))
        else:
            # No filter, show all
            matches.append((name, const_value, lineno, filepath))

    if not matches:
        print("No matching constants found.")
        return

    print(f"Found {len(matches)} matching constants:\n")

    # Group by file
    by_file: dict[str, list[tuple[str, object, int]]] = {}
    for name, const_value, lineno, filepath in matches:
        if filepath not in by_file:
            by_file[filepath] = []
        by_file[filepath].append((name, const_value, lineno))

    for filepath, consts in sorted(by_file.items()):
        print(f"{filepath}:")
        for name, const_value, lineno in sorted(consts, key=lambda x: x[2]):
            value_repr = repr(const_value) if isinstance(const_value, str) else const_value
            print(f"  L{lineno}: {name} = {value_repr}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for existing constants"
    )
    parser.add_argument(
        "value", nargs="?",
        help="Value or name to search for"
    )
    parser.add_argument(
        "--pattern", type=str,
        help="Regex pattern to match constant names"
    )
    parser.add_argument(
        "--numeric", type=float,
        help="Numeric value to search for"
    )
    parser.add_argument(
        "--path", type=Path, default=Path("src/noteflow"),
        help="Root path to search"
    )
    parser.add_argument(
        "--list-all", action="store_true",
        help="List all constants"
    )
    args = parser.parse_args()

    if not args.path.exists():
        print(f"Path not found: {args.path}")
        return

    if args.list_all:
        search_constants(args.path)
    elif args.value:
        search_constants(args.path, value=args.value)
    elif args.pattern:
        search_constants(args.path, pattern=args.pattern)
    elif args.numeric is not None:
        search_constants(args.path, numeric=args.numeric)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
