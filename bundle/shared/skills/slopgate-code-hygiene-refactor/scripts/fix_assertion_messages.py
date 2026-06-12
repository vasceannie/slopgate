#!/usr/bin/env python3
"""Generate assertion messages for tests with assertion roulette.

Usage:
    python fix_assertion_messages.py <file_path>
    python fix_assertion_messages.py tests/application/test_service.py --dry-run

Adds meaningful messages to bare assertions.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


def generate_message(assert_node: ast.Assert) -> str:
    """Generate a meaningful message for an assertion."""
    test = assert_node.test

    # assert x == y -> "Expected {left} to equal {right}"
    if isinstance(test, ast.Compare):
        left = ast.unparse(test.left)
        ops = test.ops
        comparators = test.comparators

        if len(ops) == 1:
            op = ops[0]
            right = ast.unparse(comparators[0])

            if isinstance(op, ast.Eq):
                return f"Expected {left} to equal {right}"
            elif isinstance(op, ast.NotEq):
                return f"Expected {left} to not equal {right}"
            elif isinstance(op, ast.Is):
                return f"Expected {left} to be {right}"
            elif isinstance(op, ast.IsNot):
                return f"Expected {left} to not be {right}"
            elif isinstance(op, ast.In):
                return f"Expected {left} to be in {right}"
            elif isinstance(op, ast.NotIn):
                return f"Expected {left} to not be in {right}"
            elif isinstance(op, ast.Lt):
                return f"Expected {left} to be less than {right}"
            elif isinstance(op, ast.LtE):
                return f"Expected {left} to be <= {right}"
            elif isinstance(op, ast.Gt):
                return f"Expected {left} to be greater than {right}"
            elif isinstance(op, ast.GtE):
                return f"Expected {left} to be >= {right}"

    # assert x -> "Expected {x} to be truthy"
    if isinstance(test, ast.Name):
        return f"Expected {test.id} to be truthy"

    # assert not x -> "Expected {x} to be falsy"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        operand = ast.unparse(test.operand)
        return f"Expected {operand} to be falsy"

    # assert x.attr -> "Expected {x.attr} to be truthy"
    if isinstance(test, ast.Attribute):
        return f"Expected {ast.unparse(test)} to be truthy"

    # assert callable(x) -> "Expected x to be callable"
    if isinstance(test, ast.Call):
        func_name = ""
        if isinstance(test.func, ast.Name):
            func_name = test.func.id
        elif isinstance(test.func, ast.Attribute):
            func_name = test.func.attr

        if func_name == "callable" and test.args:
            return f"Expected {ast.unparse(test.args[0])} to be callable"
        elif func_name == "isinstance" and len(test.args) >= 2:
            return f"Expected {ast.unparse(test.args[0])} to be instance of {ast.unparse(test.args[1])}"
        elif func_name == "hasattr" and len(test.args) >= 2:
            return f"Expected {ast.unparse(test.args[0])} to have attribute {ast.unparse(test.args[1])}"

    # Fallback
    return f"Assertion failed: {ast.unparse(test)}"


def process_file(file_path: Path, dry_run: bool = True) -> list[tuple[int, str, str]]:
    """Process a file and return suggested changes."""
    source = file_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}")
        return []

    changes: list[tuple[int, str, str]] = []

    # Find test functions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue

            # Count assertions without messages
            assertions_without_msg = []
            for child in ast.walk(node):
                if isinstance(child, ast.Assert) and child.msg is None:
                    assertions_without_msg.append(child)

            # Only process if multiple assertions without messages
            if len(assertions_without_msg) <= 1:
                continue

            # Generate messages for each
            for assert_node in assertions_without_msg:
                line_idx = assert_node.lineno - 1
                original_line = lines[line_idx]

                # Generate message
                msg = generate_message(assert_node)

                # Create new line with message
                indent = len(original_line) - len(original_line.lstrip())
                assertion_text = ast.unparse(assert_node.test)
                new_line = f'{" " * indent}assert {assertion_text}, "{msg}"'

                changes.append(
                    (assert_node.lineno, original_line.strip(), new_line.strip())
                )

    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Add messages to bare assertions")
    parser.add_argument("file", type=Path, help="File to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show changes without applying (default)",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes to file")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return

    changes = process_file(args.file, dry_run=not args.apply)

    if not changes:
        print(f"No assertions needing messages in {args.file}")
        return

    print(f"Found {len(changes)} assertions needing messages:\n")

    for lineno, original, suggested in changes:
        print(f"Line {lineno}:")
        print(f"  - {original}")
        print(f"  + {suggested}")
        print()

    if args.apply:
        # Read file and apply changes
        source = args.file.read_text(encoding="utf-8")
        lines = source.splitlines()

        for lineno, original, suggested in changes:
            line_idx = lineno - 1
            # Preserve indentation
            indent = len(lines[line_idx]) - len(lines[line_idx].lstrip())
            lines[line_idx] = " " * indent + suggested

        args.file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Applied {len(changes)} changes to {args.file}")
    else:
        print("Run with --apply to apply changes")


if __name__ == "__main__":
    main()
