from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint._baseline import Violation
from slopgate.rules.common.quality.lint import lint_message, violation_details


SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=20,
)


@given(identifiers=strategies.lists(SHORT_TEXT, max_size=8))
def test_violation_details_bounds_preview_and_reports_overflow_property(
    identifiers: list[str],
) -> None:
    violations = [
        Violation("manual-rule", "src/example.py", identifier, identifier)
        for identifier in identifiers
    ]

    details = violation_details("manual-rule", violations)
    final_group = details[-1] if details else []
    overflow = [line.strip() for line in final_group if " more manual-rule " in line]
    expected_overflow = (
        [f"+{len(violations) - 3} more manual-rule violation(s) not shown."]
        if len(violations) > 3
        else []
    )

    assert len(details) == min(len(violations), 3), (
        "detail previews should stay bounded"
    )
    assert overflow == expected_overflow, (
        "overflow should report the exact hidden count"
    )


@given(
    failures=strategies.lists(SHORT_TEXT, min_size=1, max_size=3, unique=True),
    targets=strategies.lists(
        SHORT_TEXT.map(lambda value: f"src/{value}.py"), min_size=1, max_size=2
    ),
)
def test_lint_message_preserves_small_failure_and_target_sets_property(
    failures: list[str],
    targets: list[str],
) -> None:
    failure_labels = [f"{failure}: 1" for failure in failures]

    message = lint_message(failure_labels, [], targets, None)

    assert all(label in message for label in failure_labels), (
        "small failure sets should remain visible in the rendered message"
    )
    assert all(target in message for target in targets), (
        "small target sets should remain visible in the rendered message"
    )
