"""Python parse-error lint collector."""
from __future__ import annotations

import ast
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import relative_path


def detect_python_parse_errors(paths: list[Path]) -> list[Violation]:
    """Return baseline-able violations for Python files that cannot be parsed."""
    violations: list[Violation] = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            line = exc.lineno or 0
            violations.append(
                Violation(
                    rule="python-parse-error",
                    relative_path=relative_path(path),
                    identifier=f"line-{line}",
                    detail=exc.msg,
                    metadata={"line": line, "offset": exc.offset or 0},
                )
            )
        except OSError as exc:
            violations.append(
                Violation(
                    rule="python-parse-error",
                    relative_path=relative_path(path),
                    identifier="read-error",
                    detail=type(exc).__name__,
                )
            )
    return violations
