from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.context import build_context
from slopgate.engine import _retry, evaluate_payload
from slopgate.models import RuleFinding, Severity
from tests.semantic_retry_support import (
    LONG_PARAMS_RULE,
    PathlessOperationCase,
    SESSION_ID,
    RetryPayloadCase,
    configure_retry_test,
    evaluate_retry_designs,
    long_params_payload,
)
from tests.test_hook_state_spec import require_finding
from tests.support import finding_ids


FIRST_DESIGN = "def build(a, b, c, d, e, f, g):\n    return a\n"
COSMETIC_DESIGN = "def build(a,b,c,d,e,f,g):\n    return a\n"
OTHER_VIOLATION = "def wrapper(a, b, c, d, e, f, g):\n    return g\n"


def test_exact_fingerprint_changes_but_semantic_repeat_count_increments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    first = evaluate_payload(long_params_payload(repo, FIRST_DESIGN))
    second = evaluate_payload(long_params_payload(repo, COSMETIC_DESIGN))

    first_metadata = require_finding(LONG_PARAMS_RULE, first.findings).metadata
    second_metadata = require_finding(LONG_PARAMS_RULE, second.findings).metadata
    assert (
        first_metadata["attempt_fingerprint"] != second_metadata["attempt_fingerprint"]
    ), "Exact diagnostics should retain cosmetic attempt differences"
    assert first_metadata["semantic_repeat_count"] == 1, (
        "First semantic violation should start at one"
    )
    assert second_metadata["semantic_repeat_count"] == 2, (
        "Cosmetic changes must not reset semantic repeat identity"
    )
    assert first_metadata["semantic_key"] == second_metadata["semantic_key"], (
        "Rule and normalized path should define stable enforcement identity"
    )


@pytest.mark.parametrize(
    "event_name",
    [
        pytest.param("PreToolUse", id="pre-tool-use"),
        pytest.param("PermissionRequest", id="permission-request"),
    ],
)
def test_cosmetic_third_retry_is_blocked_by_semantic_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    event_name: str,
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    third = evaluate_retry_designs(
        repo,
        FIRST_DESIGN,
        COSMETIC_DESIGN,
        OTHER_VIOLATION,
        case=RetryPayloadCase(event_name=event_name),
    )[-1]

    assert "RETRY-BUDGET-001" in finding_ids(third), (
        "Third semantic retry should be blocked despite cosmetic content changes"
    )


def test_retry_budget_finding_exposes_lock_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    third = evaluate_retry_designs(
        repo, FIRST_DESIGN, COSMETIC_DESIGN, OTHER_VIOLATION
    )[-1]

    metadata = require_finding("RETRY-BUDGET-001", third.findings).metadata

    assert metadata["matched_rule_ids"] == [LONG_PARAMS_RULE], (
        "Metadata should identify the locked originating rule"
    )
    assert metadata["semantic_retry_count"] == 2, (
        "Metadata should expose the count that created the lock"
    )
    assert metadata["recovery_status"] == "missing", (
        "Metadata should report why recovery was not consumed"
    )
    assert metadata["rollout"] == "deny", (
        "Metadata should expose the configured rollout action"
    )
    assert metadata["semantic_keys"], (
        "Metadata should expose the normalized enforcement identity"
    )
    assert metadata["attempt_fingerprints_locked"], (
        "Metadata should retain locked attempt fingerprints"
    )
    assert metadata["attempt_fingerprint_current"], (
        "Metadata should retain the current attempt fingerprint"
    )


def test_semantic_retry_budget_can_roll_back_to_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(
        tmp_path, monkeypatch, retry_action="context"
    )
    third = evaluate_retry_designs(
        repo, FIRST_DESIGN, COSMETIC_DESIGN, OTHER_VIOLATION
    )[-1]

    finding = require_finding("RETRY-BUDGET-001", third.findings)
    assert finding.decision is None, "Advisory rollout must not block the retry"
    assert finding.additional_context, (
        "Advisory rollout should retain recovery guidance"
    )


def test_semantic_retry_budget_can_be_disabled_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch, retry_enabled=False)
    third = evaluate_retry_designs(
        repo, FIRST_DESIGN, COSMETIC_DESIGN, OTHER_VIOLATION
    )[-1]

    assert "RETRY-BUDGET-001" not in finding_ids(third), (
        "Retry budget rollback should not delete diagnostics or trace history"
    )


def test_retry_budget_is_independent_per_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    _ = evaluate_retry_designs(repo, FIRST_DESIGN, COSMETIC_DESIGN)
    other_path = evaluate_payload(
        long_params_payload(
            repo, OTHER_VIOLATION, RetryPayloadCase(target="src/other.py")
        )
    )
    assert "RETRY-BUDGET-001" not in finding_ids(other_path), (
        "A different path should have an independent semantic budget"
    )
    assert (
        require_finding(LONG_PARAMS_RULE, other_path.findings).metadata[
            "semantic_repeat_count"
        ]
        == 1
    ), "A different path should begin a fresh semantic counter"


def test_retry_budget_is_independent_per_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    _ = evaluate_retry_designs(repo, FIRST_DESIGN, COSMETIC_DESIGN)
    thin_wrapper = (
        "def target(value):\n    return value\n\n\n"
        "def wrap(value):\n    return target(value)\n"
    )

    other_rule = evaluate_payload(long_params_payload(repo, thin_wrapper))

    assert "RETRY-BUDGET-001" not in finding_ids(other_rule), (
        "A different rule on the locked path should remain independent"
    )
    assert "PY-CODE-013" in finding_ids(other_rule), (
        "The independent rule should still report its own finding"
    )


def test_prompt_keyword_signal_does_not_unlock_retry_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    _ = evaluate_retry_designs(repo, FIRST_DESIGN, COSMETIC_DESIGN)
    _ = evaluate_payload(
        {
            "session_id": SESSION_ID,
            "cwd": str(repo),
            "hook_event_name": "UserPromptSubmit",
            "tool_name": "",
            "tool_input": {},
            "prompt": "repair plan: reread rules and constraints before write",
        }
    )

    third = evaluate_retry_designs(repo, OTHER_VIOLATION)[0]

    assert "RETRY-BUDGET-001" in finding_ids(third), (
        "Prompt substrings must not unlock semantic retry state"
    )


def test_confirmed_clear_resets_semantic_count_before_reintroduction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    _first, _second, clear, reintroduced = evaluate_retry_designs(
        repo,
        FIRST_DESIGN,
        COSMETIC_DESIGN,
        "def build(request):\n    return request\n",
        OTHER_VIOLATION,
    )

    assert LONG_PARAMS_RULE not in finding_ids(clear), (
        "A clean design should confirm the semantic violation cleared"
    )
    assert (
        require_finding(LONG_PARAMS_RULE, reintroduced.findings).metadata[
            "semantic_repeat_count"
        ]
        == 1
    ), "Reintroduced debt should start a fresh semantic counter"


@pytest.mark.parametrize(
    "case",
    [
        PathlessOperationCase(
            "ApplyPatch", {"content": "no extractable file header"}, "edit"
        ),
        PathlessOperationCase("Bash", {"command": "set +e"}, "shell"),
    ],
    ids=("edit", "shell"),
)
def test_pathless_semantic_identity_uses_operation_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: PathlessOperationCase,
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    finding = RuleFinding(
        rule_id="PATHLESS-001",
        title="Pathless rule",
        severity=Severity.HIGH,
        decision="deny",
    )
    ctx = build_context(
        {
            "session_id": SESSION_ID,
            "cwd": str(repo),
            "hook_event_name": "PreToolUse",
            "tool_name": case.tool_name,
            "tool_input": case.tool_input,
        }
    )
    key = _retry.semantic_enforcement_key(ctx, finding)

    assert key.path is None, "Pathless findings should keep a null path"
    assert key.operation_category == case.expected_category, (
        "Pathless attempts should normalize to their operation category"
    )
