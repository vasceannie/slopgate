from __future__ import annotations

from uuid import uuid4

from hypothesis import given, strategies

from slopgate.context import build_context
from slopgate.engine._hints import (
    compress_repeated_import_alias_examples,
    quality_lint_hint,
)
from slopgate.models import RuleFinding, Severity

ALIAS_EXAMPLES = (
    "Only canonical library aliases are allowed, e.g. `pandas as pd`, "
    "`polars as pl`, `numpy as np`, or `matplotlib.pyplot as plt`."
)
REPLACEMENT_TEXT = "Use this instead:\n    from app.services import resolver"
ALIAS_CONTEXT = build_context(
    {
        "session_id": f"hypothesis-import-alias-{uuid4().hex}",
        "cwd": ".",
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {},
    }
)
QUALITY_CONTEXTS = {
    event_name: build_context(
        {
            "session_id": f"hypothesis-quality-lint-{event_name}",
            "cwd": ".",
            "hook_event_name": event_name,
            "tool_name": "Write",
            "tool_input": {},
        }
    )
    for event_name in ("PreToolUse", "PostToolUse")
}
QUALITY_FINDINGS = strategies.builds(
    RuleFinding,
    rule_id=strategies.just("QUALITY-LINT-001"),
    title=strategies.just("Touched-file lint failed"),
    severity=strategies.just(Severity.HIGH),
    metadata=strategies.fixed_dictionaries(
        {
            "failing_collectors": strategies.lists(
                strategies.sampled_from(
                    [
                        "oversized-module-soft: 1",
                        "untested-production-code: 1",
                        "other: 1",
                    ]
                ),
                min_size=1,
                max_size=1,
            )
        },
        optional={"path": strategies.just("src/example.py")},
    ),
)


@given(prefix=strategies.text(max_size=20), suffix=strategies.text(max_size=20))
def test_import_alias_example_compression_is_idempotent(
    prefix: str, suffix: str
) -> None:
    finding = RuleFinding(
        rule_id="PY-IMPORT-002",
        title="Block non-standard Python import aliases",
        severity=Severity.HIGH,
        message=f"{prefix}{ALIAS_EXAMPLES}\n\n{REPLACEMENT_TEXT}{suffix}",
    )

    compress_repeated_import_alias_examples(ALIAS_CONTEXT, finding)
    compress_repeated_import_alias_examples(ALIAS_CONTEXT, finding)
    compressed_once = finding.message
    compress_repeated_import_alias_examples(ALIAS_CONTEXT, finding)

    assert finding.message == compressed_once, (
        "alias example compression should be idempotent after repeat state is set"
    )
    assert REPLACEMENT_TEXT in (finding.message or ""), (
        "alias example compression should preserve exact replacement guidance"
    )


@given(
    event_name=strategies.sampled_from(["PreToolUse", "PostToolUse"]),
    finding=QUALITY_FINDINGS,
)
def test_quality_lint_hint_keeps_core_recovery_guidance(
    event_name: str, finding: RuleFinding
) -> None:
    hint = quality_lint_hint(QUALITY_CONTEXTS[event_name], finding)

    assert "slopgate lint check" in hint, (
        "quality lint hint should always include repo-root lint verification"
    )
