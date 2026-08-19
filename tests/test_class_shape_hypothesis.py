"""Hypothesis references for class-shape AST helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.python_ast._rules.class_shape import (
    PythonGodClassRule,
    PythonThinWrapperRule,
    is_wrapper_candidate,
    thin_wrapper_extract_single_call,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_class_shape_helper_names(value: int) -> None:
    assert (
        PythonGodClassRule.__name__,
        PythonThinWrapperRule.__name__,
        is_wrapper_candidate.__name__,
        thin_wrapper_extract_single_call.__name__,
        value,
    )[-1] == value
