"""Shared CLI input and output helpers."""

from __future__ import annotations

import json
import sys
from typing import cast

from slopgate._types import ObjectDict, ObjectMapping, object_dict


class CliInputError(ValueError):
    """Clean user-facing CLI input error."""


def stdin_is_interactive() -> bool:
    isatty = getattr(sys.stdin, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def load_stdin_json() -> ObjectDict:
    if stdin_is_interactive():
        raise CliInputError(
            "No JSON payload on stdin. 'slopgate handle' is a hook entrypoint; pipe a harness payload, e.g. echo '{}' | slopgate handle --platform cursor"
        )
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        parsed = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise CliInputError(f"Invalid JSON on stdin: {exc.msg}") from None
    return object_dict(parsed)


def report_cli_input_error(exc: CliInputError) -> int:
    print(str(exc), file=sys.stderr)
    return 1


def string_arg(args: object, name: str, default: str = "") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def dump_output(output: ObjectMapping | None) -> int:
    if output:
        _ = sys.stdout.write(json.dumps(output, separators=(",", ":")) + "\n")
    return 0


__all__ = [
    "CliInputError",
    "dump_output",
    "load_stdin_json",
    "report_cli_input_error",
    "string_arg",
    "stdin_is_interactive",
]
