"""Shared CLI input and output helpers."""

from __future__ import annotations

import codecs
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
    raw = _read_stdin_text()
    if not raw.strip():
        return {}
    try:
        parsed = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise CliInputError(f"Invalid JSON on stdin: {exc.msg}") from None
    return object_dict(parsed)


def _read_stdin_text() -> str:
    """Decode hook payload bytes as UTF-8 (JSON's wire encoding), not the locale code page."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    data = cast(bytes, buffer.read())
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # utf-8-sig reports offsets after the stripped BOM; report stdin offsets.
        bom = len(codecs.BOM_UTF8) if data.startswith(codecs.BOM_UTF8) else 0
        raise CliInputError(
            f"Invalid UTF-8 on stdin at byte {bom + exc.start}: {exc.reason}"
        ) from None


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
