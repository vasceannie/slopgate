from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies

from slopgate.adapters import base
from slopgate.models import RuleFinding, Severity


_FINDING = RuleFinding(
    rule_id="TEST",
    title="Test finding",
    severity=Severity.HIGH,
    decision="deny",
    message="blocked",
)
_json_scalars = strategies.one_of(
    strategies.none(),
    strategies.booleans(),
    strategies.integers(),
    strategies.text(),
)
_updated_input_values = strategies.dictionaries(
    strategies.text(min_size=1),
    _json_scalars,
    max_size=5,
)


@given(event_name=strategies.text(min_size=1))
def test_render_request_from_call_preserves_event_name_property(
    event_name: str,
) -> None:
    request = base.render_request_from_call(
        (event_name, [_FINDING]),
        {},
    )

    assert request.event_name == event_name


@given(updated_input=_updated_input_values)
def test_render_request_from_call_preserves_updated_input_property(
    updated_input: dict[str, object],
) -> None:
    request = base.render_request_from_call(
        ("PreToolUse", [_FINDING]),
        {"updated_input": updated_input},
    )

    assert request.updated_input == updated_input


@given(
    unexpected_key=strategies.text(min_size=1).filter(lambda value: value != "context")
)
def test_render_request_from_call_rejects_unknown_keywords_property(
    unexpected_key: str,
) -> None:
    with pytest.raises(TypeError, match="unexpected render_output keyword"):
        base.render_request_from_call(
            ("PreToolUse", [_FINDING]),
            {unexpected_key: "value"},
        )
