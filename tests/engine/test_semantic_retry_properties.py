from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import assume, given, strategies

from slopgate.context import build_context
from slopgate.engine._retry.guidance import recovery_guidance
from slopgate.engine._retry.identity import (
    attempt_fingerprint,
    operation_category,
    semantic_enforcement_key,
)
from slopgate.models import RuleFinding, Severity


IDENTIFIER = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True)
CONTENT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-\n",
    max_size=80,
)
CWD = str(Path.cwd())


@given(rule_id=strategies.sampled_from(("PY-CODE-013", "PY-LOG-002", "SHELL-001")))
def test_recovery_guidance_normalizes_rule_identity_property(rule_id: str) -> None:
    canonical = recovery_guidance(rule_id)

    normalized = recovery_guidance(f"  {rule_id.lower()}  ")

    assert normalized == canonical, (
        "rule identity normalization should preserve guidance"
    )


@given(
    tool_name=strategies.sampled_from(("Bash", "Shell", "PowerShell", "Read", "Grep"))
)
def test_operation_category_is_case_and_whitespace_invariant_property(
    tool_name: str,
) -> None:
    canonical = operation_category(
        build_context(
            {
                "session_id": "property-session",
                "cwd": CWD,
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {"file_path": "src/app.py"},
            }
        )
    )
    normalized = operation_category(
        build_context(
            {
                "session_id": "property-session",
                "cwd": CWD,
                "hook_event_name": "PreToolUse",
                "tool_name": f"  {tool_name.swapcase()}  ",
                "tool_input": {"file_path": "src/app.py"},
            }
        )
    )

    assert normalized == canonical, (
        "tool-name formatting should not change its category"
    )


@given(target=IDENTIFIER, first=CONTENT, second=CONTENT)
def test_attempt_fingerprint_changes_with_distinct_content_property(
    target: str,
    first: str,
    second: str,
) -> None:
    assume(first != second)
    path = f"src/{target}.py"
    first_fingerprint = attempt_fingerprint(
        build_context(
            {
                "session_id": "property-session",
                "cwd": CWD,
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": first},
            }
        )
    )
    second_fingerprint = attempt_fingerprint(
        build_context(
            {
                "session_id": "property-session",
                "cwd": CWD,
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": second},
            }
        )
    )

    assert first_fingerprint != second_fingerprint, (
        "distinct proposed content should keep distinct exact fingerprints"
    )


@given(target=IDENTIFIER)
def test_semantic_enforcement_key_normalizes_equivalent_paths_property(
    target: str,
) -> None:
    with TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        relative = f"src/{target}.py"
        finding = RuleFinding(
            rule_id="  PY-CODE-009  ",
            title="Long parameter list",
            severity=Severity.HIGH,
            metadata={"path": relative},
        )
        key = semantic_enforcement_key(
            build_context(
                {
                    "session_id": " property-session ",
                    "cwd": str(root),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": relative},
                }
            ),
            finding,
        )

    assert key.session_id == "property-session", "session identity should be trimmed"
    assert key.rule_id == "PY-CODE-009", "rule identity should be trimmed"
    assert key.path == str((root / relative).resolve()), (
        "semantic paths should be repository-absolute"
    )
    assert key.operation_category is None, (
        "path-backed identities should not need a category"
    )
