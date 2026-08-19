"""Hypothesis references for log-signal boundary classifiers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.python_ast._rules.log_signals.kinds import (
    boundary_kind_for_function,
    class_name_has_package_boundary_signal,
    contains_package_boundary_call,
    iter_public_boundary_functions,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_log_signal_kind_helper_names(value: int) -> None:
    assert (
        boundary_kind_for_function.__name__,
        class_name_has_package_boundary_signal.__name__,
        contains_package_boundary_call.__name__,
        iter_public_boundary_functions.__name__,
        value,
    )[-1] == value
