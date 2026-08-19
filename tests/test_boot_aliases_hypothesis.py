"""Hypothesis references for early module-alias helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.boot_aliases import (
    install_private_name_finder,
    install_source_parse_alias,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_boot_alias_helper_names(value: int) -> None:
    assert (
        install_private_name_finder.__name__,
        install_source_parse_alias.__name__,
        value,
    )[-1] == value
