"""Tests for declarative repeated-block policy."""

from __future__ import annotations
import ast
from typing import cast
from hypothesis import given
from hypothesis import strategies
from slopgate.lint._detectors.declarative import (
    is_constant_name,
    is_declarative_constant_stmt,
    is_declarative_constant_value,
    should_skip_block_window,
)


def _module_body(source: str) -> list[ast.stmt]:
    return ast.parse(source).body


def test_declarative_constant_helpers_accept_safe_constant_shapes() -> None:
    """Readable constant declarations are explicit policy, not hash hacks."""
    body = _module_body(
        '_TEXT_SUFFIXES = frozenset({".md", ".txt"})\n_UNKNOWN_SUFFIX = "".join(("un", "known"))\n_STATUS_OK = cast(Status, "ok")\n'
    )
    status = (
        is_constant_name("_TEXT_SUFFIXES"),
        all((is_declarative_constant_stmt(stmt) for stmt in body)),
        is_declarative_constant_value(cast(ast.Assign, body[1]).value),
        should_skip_block_window(body, range(0, 3), "<module>", set()),
    )
    assert status == (True, True, True, True)


def test_declarative_window_accepts_standard_logger_plus_constants() -> None:
    """Top-level logger setup plus constants is module scaffold, not behavior."""
    body = _module_body(
        'logger = get_logger(__name__)\n_FRAME_DEPTH_FMT = "Switched to frame {} (depth {})"\n_FIELD_DISCOVERED_FMT = "Field discovered: {} ({})"\n'
    )
    assert should_skip_block_window(body, range(0, 3), "<module>", set())


def test_declarative_window_rejects_logger_plus_side_effects() -> None:
    """Logger setup must not hide executable module-level behavior."""
    body = _module_body(
        'logger = get_logger(__name__)\nregister("resume")\nconnect(client)\n'
    )
    assert should_skip_block_window(body, range(0, 3), "<module>", set()) is False


def test_declarative_window_rejects_dynamic_logger_factory_argument() -> None:
    """Only conventional logger = get_logger(__name__) is declarative scaffold."""
    body = _module_body(
        'logger = get_logger(runtime_name)\n_FRAME_DEPTH_FMT = "Switched to frame {} (depth {})"\n_FIELD_DISCOVERED_FMT = "Field discovered: {} ({})"\n'
    )
    assert should_skip_block_window(body, range(0, 3), "<module>", set()) is False


@given(strategies.text(max_size=20))
def test_declarative_constant_helpers_accept_literal_string_properties(
    value: str,
) -> None:
    """Literal constants remain declarative for arbitrary string payloads."""
    body = _module_body(
        f"_VALUE = {value!r}\n_ALIAS = _VALUE\n_PAIR = ({value!r}, _VALUE)\n"
    )
    status = (
        all((is_declarative_constant_stmt(stmt) for stmt in body)),
        is_declarative_constant_value(cast(ast.Assign, body[2]).value),
        should_skip_block_window(body, range(0, 3), "<module>", set()),
    )
    assert status == (True, True, True)
