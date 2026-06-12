#!/usr/bin/env python3
"""Analyze long functions and suggest extraction points.

Usage:
    python analyze_long_functions.py <file_path>
    python analyze_long_functions.py src/noteflow/grpc/service.py --threshold 40

Identifies logical blocks that could be extracted into helper functions.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    """A logical block within a function."""

    start_line: int
    end_line: int
    type: str
    description: str
    extractable: bool


def analyze_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
) -> list[Block]:
    """Analyze a function for extractable blocks."""
    blocks: list[Block] = []

    for node in ast.iter_child_nodes(func):
        # Try/except blocks
        if isinstance(node, ast.Try):
            end = node.end_lineno or node.lineno
            blocks.append(
                Block(
                    start_line=node.lineno,
                    end_line=end,
                    type="try_block",
                    description="Error handling block",
                    extractable=end - node.lineno > 5,
                )
            )

        # For loops
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            end = node.end_lineno or node.lineno
            blocks.append(
                Block(
                    start_line=node.lineno,
                    end_line=end,
                    type="loop",
                    description=f"Loop over {ast.unparse(node.iter)[:30]}",
                    extractable=end - node.lineno > 5,
                )
            )

        # If blocks
        elif isinstance(node, ast.If):
            end = node.end_lineno or node.lineno
            condition = ast.unparse(node.test)[:40]
            blocks.append(
                Block(
                    start_line=node.lineno,
                    end_line=end,
                    type="conditional",
                    description=f"If {condition}",
                    extractable=end - node.lineno > 8,
                )
            )

        # With blocks
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            end = node.end_lineno or node.lineno
            blocks.append(
                Block(
                    start_line=node.lineno,
                    end_line=end,
                    type="context_manager",
                    description="Context manager block",
                    extractable=end - node.lineno > 10,
                )
            )

    return blocks


def find_long_functions(
    file_path: Path,
    threshold: int = 50,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, int, list[Block]]]:
    """Find functions exceeding the threshold."""
    source = file_path.read_text(encoding="utf-8")
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, int, list[Block]]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno is None:
                continue

            length = node.end_lineno - node.lineno + 1
            if length > threshold:
                blocks = analyze_function(node, source_lines)
                results.append((node, length, blocks))

    return sorted(results, key=lambda x: -x[1])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze long functions for extraction opportunities"
    )
    parser.add_argument("file", type=Path, help="File to analyze")
    parser.add_argument(
        "--threshold", type=int, default=50, help="Line threshold for long functions"
    )
    parser.add_argument(
        "--show-code",
        action="store_true",
        help="Show code preview for extractable blocks",
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    results = find_long_functions(args.file, args.threshold)

    if not results:
        print(f"No functions over {args.threshold} lines in {args.file}")
        return

    source_lines = args.file.read_text(encoding="utf-8").splitlines()

    print(f"Long functions in {args.file}:\n")

    for func, length, blocks in results:
        async_prefix = "async " if isinstance(func, ast.AsyncFunctionDef) else ""
        print(f"{'=' * 60}")
        print(f"{async_prefix}def {func.name}() - {length} lines")
        print(f"  Location: {args.file}:{func.lineno}-{func.end_lineno}")

        extractable = [b for b in blocks if b.extractable]
        if extractable:
            print(f"\n  Extractable blocks ({len(extractable)}):")
            for block in extractable:
                block_len = block.end_line - block.start_line + 1
                print(
                    f"    - Lines {block.start_line}-{block.end_line} ({block_len} lines)"
                )
                print(f"      Type: {block.type}")
                print(f"      Description: {block.description}")

                if args.show_code:
                    print("      Preview:")
                    preview_lines = source_lines[
                        block.start_line - 1 : block.start_line + 2
                    ]
                    for line in preview_lines:
                        print(f"        {line}")
                    if block.end_line - block.start_line > 3:
                        print("        ...")

        # Suggest extraction names
        if extractable:
            print("\n  Suggested helper functions:")
            for i, block in enumerate(extractable, 1):
                if block.type == "loop":
                    print(f"    - _process_{func.name}_items()")
                elif block.type == "try_block":
                    print(f"    - _handle_{func.name}_errors()")
                elif block.type == "conditional":
                    print(f"    - _handle_{func.name}_case_{i}()")
                elif block.type == "context_manager":
                    print(f"    - _with_{func.name}_context()")

        print()


if __name__ == "__main__":
    main()
