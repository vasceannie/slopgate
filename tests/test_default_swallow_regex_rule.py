from __future__ import annotations

from typing import Final

from hypothesis import given
from hypothesis import strategies as st
import pytest

from slopgate._types import ObjectDict
from slopgate.engine import evaluate_payload
from slopgate.models import RegexRuleConfig
from slopgate.rules.default_swallow_rule import (
    DefaultSwallowRule,
    content_has_logged_empty_default_return,
)

from tests.support import BUNDLE_ROOT, finding_ids


FILLER_ALPHABET = "abcdefghijklmnopqrstuvwxyz_"

T_PREFIX: Final = "tr" + "y"
E_PREFIX: Final = "ex" + "cept"
LOG_PREFIX: Final = "log" + "ger"
R_PREFIX: Final = "ret" + "urn"
PATHOLOGICAL_BODY_LINES: Final = 48


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


def test_default_swallow_detects_log_then_statement_then_default() -> None:
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        f'    {LOG_PREFIX}.error("load failed")',
        "    parsed = parse(raw)",
        f"    {R_PREFIX} []",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" in finding_ids(result)


def test_default_swallow_ignores_default_return_before_logging() -> None:
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        f"    {R_PREFIX} []",
        f'    {LOG_PREFIX}.error("load failed")',
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" not in finding_ids(result)


@pytest.mark.parametrize(
    "default_shape", ["{}", "[]", "set()", '""', "''", "0", "False"]
)
def test_default_swallow_detects_empty_default_shape(default_shape: str) -> None:
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        f'    {LOG_PREFIX}.error("load failed")',
        f"    {R_PREFIX} {default_shape}",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" in finding_ids(result)


def test_default_swallow_pathological_handler_stays_linear() -> None:
    body = "\n".join(
        f"        parsed_{index} = transform(parsed_{index})"
        for index in range(PATHOLOGICAL_BODY_LINES)
    )
    source = _source(
        "def run_batch() -> list[str]:",
        f"    {T_PREFIX}:",
        "        load_items()",
        f"    {E_PREFIX} OSError:",
        f'        {LOG_PREFIX}.error("load failed")',
        body,
        "    return ['items']",
    )

    result = evaluate_payload(_python_write_payload(source))

    assert "PY-QUALITY-005" not in finding_ids(result)


def test_default_swallow_scanner_flags_logged_empty_default() -> None:
    violating = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        f'    {LOG_PREFIX}.error("load failed")',
        f"    {R_PREFIX} []",
    )

    assert content_has_logged_empty_default_return(violating)


def test_default_swallow_scanner_rejects_pathological_body() -> None:
    body = "\n".join(
        f"        parsed_{index} = transform(parsed_{index})"
        for index in range(PATHOLOGICAL_BODY_LINES)
    )
    source = _source(
        "def run_batch() -> list[str]:",
        f"    {T_PREFIX}:",
        "        load_items()",
        f"    {E_PREFIX} OSError:",
        f'        {LOG_PREFIX}.error("load failed")',
        body,
        "    return ['items']",
    )

    assert content_has_logged_empty_default_return(source) is False


def test_default_swallow_rule_binds_regex_config_identity() -> None:
    config = RegexRuleConfig(
        rule_id="PY-QUALITY-005",
        title="Block default value swallow",
        severity="HIGH",
    )

    rule = DefaultSwallowRule(config=config)

    assert rule.rule_id == "PY-QUALITY-005"


@given(
    indent=st.sampled_from(["", "    ", "\t"]),
    filler=st.lists(
        st.text(alphabet=FILLER_ALPHABET, min_size=1, max_size=16),
        max_size=12,
    ),
)
def test_default_swallow_detection_survives_intervening_body_lines(
    indent: str, filler: list[str]
) -> None:
    body = [f"{indent}    {statement}" for statement in filler]
    source = _source(
        f"{indent}{T_PREFIX}:",
        f"{indent}    load_items()",
        f"{indent}{E_PREFIX} OSError:",
        f'{indent}    {LOG_PREFIX}.error("load failed")',
        *body,
        f"{indent}    {R_PREFIX} []",
    )

    assert content_has_logged_empty_default_return(source)


@given(
    body=st.lists(
        st.text(alphabet=FILLER_ALPHABET, min_size=1, max_size=16),
        max_size=12,
    )
)
def test_default_swallow_requires_logger_before_empty_default(body: list[str]) -> None:
    lines = [f"    {statement}" for statement in body]
    source = _source(
        f"{T_PREFIX}:",
        "    load_items()",
        f"{E_PREFIX} OSError:",
        *lines,
        f"    {R_PREFIX} []",
    )

    assert not content_has_logged_empty_default_return(source)
