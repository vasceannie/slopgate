#!/usr/bin/env python3
"""Find similar or duplicate functions in the codebase.

Usage:
    python find_similar_functions.py [--threshold 0.8] [--path src/]

Outputs functions with similar bodies for consolidation review.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


@dataclass
class FunctionInfo:
    """Metadata about a function for comparison."""

    file_path: Path
    name: str
    lineno: int
    end_lineno: int
    body_hash: str
    normalized_body: str
    param_count: int
    is_async: bool

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.lineno}"

    @property
    def qualified_name(self) -> str:
        return f"{self.file_path.stem}.{self.name}"


def normalize_ast(code: str) -> str:
    """Normalize AST for comparison by replacing variable names."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    class Normalizer(ast.NodeTransformer):
        def __init__(self) -> None:
            self.var_counter = 0
            self.var_map: dict[str, str] = {}

        def visit_Name(self, node: ast.Name) -> ast.Name:
            if node.id not in self.var_map:
                self.var_map[node.id] = f"VAR{self.var_counter}"
                self.var_counter += 1
            node.id = self.var_map[node.id]
            return node

        def visit_arg(self, node: ast.arg) -> ast.arg:
            if node.arg not in self.var_map:
                self.var_map[node.arg] = f"VAR{self.var_counter}"
                self.var_counter += 1
            node.arg = self.var_map[node.arg]
            return node

    normalizer = Normalizer()
    normalized = normalizer.visit(tree)
    return ast.dump(normalized)


def extract_functions(file_path: Path) -> list[FunctionInfo]:
    """Extract function info from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    functions: list[FunctionInfo] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno is None:
                continue

            # Skip very short functions (< 5 lines)
            if node.end_lineno - node.lineno < 5:
                continue

            body_lines = lines[node.lineno - 1 : node.end_lineno]
            body_text = "\n".join(body_lines)
            normalized = normalize_ast(body_text)
            body_hash = hashlib.md5(normalized.encode()).hexdigest()

            param_count = len(node.args.args) + len(node.args.kwonlyargs)

            functions.append(
                FunctionInfo(
                    file_path=file_path,
                    name=node.name,
                    lineno=node.lineno,
                    end_lineno=node.end_lineno,
                    body_hash=body_hash,
                    normalized_body=normalized,
                    param_count=param_count,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                )
            )

    return functions


def similarity_ratio(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def find_python_files(root: Path) -> list[Path]:
    """Find Python files excluding generated and test files."""
    excluded = {"*_pb2.py", "*_pb2_grpc.py", "*_pb2.pyi", "conftest.py"}
    files: list[Path] = []

    for py_file in root.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        if "migrations" in py_file.parts:
            continue
        if any(py_file.match(p) for p in excluded):
            continue
        files.append(py_file)

    return files


def find_duplicates(
    functions: list[FunctionInfo],
) -> dict[str, list[FunctionInfo]]:
    """Find exact duplicate functions by hash."""
    by_hash: dict[str, list[FunctionInfo]] = defaultdict(list)
    for func in functions:
        by_hash[func.body_hash].append(func)

    return {h: funcs for h, funcs in by_hash.items() if len(funcs) > 1}


def find_similar(
    functions: list[FunctionInfo], threshold: float = 0.8
) -> list[tuple[FunctionInfo, FunctionInfo, float]]:
    """Find similar (but not exact) duplicate functions."""
    similar: list[tuple[FunctionInfo, FunctionInfo, float]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, f1 in enumerate(functions):
        for f2 in functions[i + 1 :]:
            # Skip if same hash (exact duplicates handled separately)
            if f1.body_hash == f2.body_hash:
                continue

            # Skip if already seen this pair
            loc_a, loc_b = sorted((f1.location, f2.location))
            pair_key = (loc_a, loc_b)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            ratio = similarity_ratio(f1.normalized_body, f2.normalized_body)
            if ratio >= threshold:
                similar.append((f1, f2, ratio))

    return sorted(similar, key=lambda x: -x[2])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find similar or duplicate functions"
    )
    parser.add_argument(
        "--path", type=Path, default=Path("src/noteflow"),
        help="Root path to search"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.8,
        help="Similarity threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--include-tests", action="store_true",
        help="Include test files in search"
    )
    args = parser.parse_args()

    root = args.path
    if not root.exists():
        print(f"Path not found: {root}")
        return

    print(f"Scanning {root}...")
    files = find_python_files(root)

    if args.include_tests:
        test_root = root.parent.parent / "tests"
        if test_root.exists():
            files.extend(find_python_files(test_root))

    all_functions: list[FunctionInfo] = []
    for f in files:
        all_functions.extend(extract_functions(f))

    print(f"Found {len(all_functions)} functions in {len(files)} files\n")

    # Exact duplicates
    duplicates = find_duplicates(all_functions)
    if duplicates:
        print("=" * 60)
        print("EXACT DUPLICATES (identical normalized body)")
        print("=" * 60)
        for hash_val, funcs in duplicates.items():
            print(f"\nDuplicate group (hash: {hash_val[:8]}...):")
            for f in funcs:
                print(f"  - {f.name} at {f.location}")
                print(f"    Lines: {f.lineno}-{f.end_lineno} ({f.end_lineno - f.lineno + 1} lines)")
    else:
        print("No exact duplicates found.\n")

    # Similar functions
    similar = find_similar(all_functions, args.threshold)
    if similar:
        print("\n" + "=" * 60)
        print(f"SIMILAR FUNCTIONS (>= {args.threshold:.0%} similarity)")
        print("=" * 60)
        for f1, f2, ratio in similar[:20]:  # Top 20
            print(f"\n{ratio:.1%} similar:")
            print(f"  1. {f1.name} at {f1.location}")
            print(f"  2. {f2.name} at {f2.location}")
    else:
        print(f"No similar functions above {args.threshold:.0%} threshold.\n")


if __name__ == "__main__":
    main()
