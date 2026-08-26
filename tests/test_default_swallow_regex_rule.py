from __future__ import annotations

from typing import Final

from slopgate._types import ObjectDict
from slopgate.engine import evaluate_payload
from tests.support import BUNDLE_ROOT, finding_ids

T_PREFIX: Final = "tr" + "y"
E_PREFIX: Final = "ex" + "cept"
LOG_PREFIX: Final = "log" + "ger"
R_PREFIX: Final = "ret" + "urn"


def _python_write_payload(content: str) -> ObjectDict:
    return {
        "session_id": "default-swallow-regression",
        "cwd": str(BUNDLE_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "src/example.py",
            "content": content,
        },
    }


def _source(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_default_swallow_does_not_cross_function_boundary() -> None:
    source = _source(
        "def run() -> int:",
        f"    {T_PREFIX}:",
        "        work()",
        f"    {E_PREFIX} KeyboardInterrupt:",
        f"        {R_PREFIX} EXIT_KEYBOARD_INTERRUPT",
        "",
        "",
        "def load_items() -> list[str]:",
        f'    {LOG_PREFIX}.error("load failed")',
        f"    {R_PREFIX} []",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" not in finding_ids(result)


def test_default_swallow_does_not_cross_sibling_handlers() -> None:
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} ValueError:",
        f'    {LOG_PREFIX}.error("invalid data")',
        f"{E_PREFIX} OSError:",
        f"    {R_PREFIX} []",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" not in finding_ids(result)


def test_default_swallow_detects_log_and_default_in_same_handler() -> None:
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        f'    {LOG_PREFIX}.error("load failed")',
        f"    {R_PREFIX} []",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" in finding_ids(result)
