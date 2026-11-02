from __future__ import annotations

import pytest
from hypothesis import given, strategies

from slopgate.adapters.opencode_projection.exact import replace_text


@pytest.mark.parametrize(
    ("source", "change", "expected"),
    [
        ("x x\n", ("x", "y", False), None),
        ("x x\n", ("x", "y", True), "y y\n"),
        ("print(‘x’)\n", ("print('x')", "print('y')", False), "print('y')\n"),
        ("a  \nb\n", ("a\nb", "c\nb", False), "c\nb\n"),
        ("a\r\nb\r\n", ("a\nb", "c\nb", False), "c\r\nb\r\n"),
        ("a\r\nb\nc\r\n", ("a\nb\nc", "A\nb\nC", False), "A\r\nb\nC\r\n"),
        ("a\r\n", ("a\r\n", "a\n", False), "a\n"),
        ("a\n", ("", "b", False), None),
        ("a\n", ("a", "a", False), None),
        ("a\n", ("missing", "b", False), None),
    ],
)
def test_native_exact_edit_matching_preserves_consumer_visible_bytes(
    source: str, change: tuple[str, str, bool], expected: str | None
) -> None:
    assert replace_text(source, *change) == expected, (
        "projection must match native uniqueness, normalization and line-ending behavior"
    )


@given(strategies.text(alphabet=strategies.characters(blacklist_characters="\r")))
def test_exact_edit_retains_unmatched_prefix_and_suffix(replacement: str) -> None:
    old = "TOKEN"
    source = "prefix\nTOKEN\nsuffix\n"
    result = replace_text(source, old, replacement, False)
    expected = source.replace(old, replacement)
    assert result == (None if expected == source else expected), (
        "exact replacement must preserve all bytes outside the matched region"
    )
