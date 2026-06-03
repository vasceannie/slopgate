from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, strategies

import vibeforcer.lint._baseline
from vibeforcer.adapters.base import (
    hook_specific_context_output,
    render_permission_request_output,
)
from vibeforcer.lint._baseline import (
    BaselineResult,
    Violation,
    content_hash,
    load_baseline,
    save_baseline,
)
from vibeforcer.state._models import RetryLockPayload
from vibeforcer.util.payloads._patches import (
    extract_added_patch_content,
    parse_patch_candidate_paths,
)
from vibeforcer.util.subprocesses import CommandResult, run_shell


def test_retry_lock_payload_keeps_retry_state_fields() -> None:
    payload = RetryLockPayload(
        repeated_rule_ids=["PY-CODE-013"],
        current_rule_ids=["PY-CODE-013", "PY-CODE-015"],
        paths=["src/example.py"],
        attempt_fingerprint="fingerprint-1",
        count=3,
    )

    assert payload == RetryLockPayload(
        repeated_rule_ids=["PY-CODE-013"],
        current_rule_ids=["PY-CODE-013", "PY-CODE-015"],
        paths=["src/example.py"],
        attempt_fingerprint="fingerprint-1",
        count=3,
    )


def test_run_shell_returns_command_result_for_real_subprocess(tmp_path: Path) -> None:
    result = run_shell(
        "printf 'hello' && printf 'oops' >&2",
        tmp_path,
        timeout=5,
    )

    assert result == CommandResult(
        command="printf 'hello' && printf 'oops' >&2",
        cwd=str(tmp_path),
        returncode=0,
        stdout="hello",
        stderr="oops",
    )


def test_patch_helpers_extract_unique_paths_and_added_content() -> None:
    patch_blob = "\n".join(
        [
            "diff --git a/src/old.py b/src/new.py",
            "--- a/src/old.py",
            "+++ b/src/new.py",
            "+added line",
            "*** Update File: tests/test_new.py",
            "+assert True",
            "--- /dev/null",
            "+++ b/src/new.py",
        ]
    )

    assert parse_patch_candidate_paths(patch_blob) == [
        "src/old.py",
        "src/new.py",
        "tests/test_new.py",
    ]
    assert extract_added_patch_content(patch_blob) == "added line\nassert True"


def test_adapter_base_renders_context_and_permission_decisions() -> None:
    context_output = hook_specific_context_output("PreToolUse", "read files first")
    deny_output = render_permission_request_output(
        "PermissionRequest",
        "deny",
        "blocked by policy",
    )
    allow_output = render_permission_request_output(
        "PermissionRequest",
        "allow",
        "approved",
        updated_input={"tool": "Read"},
    )

    assert context_output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "read files first",
        }
    }
    assert deny_output == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": "blocked by policy"},
        }
    }
    assert allow_output == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow", "updatedInput": {"tool": "Read"}},
        }
    }


def test_save_baseline_writes_sorted_stable_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "baselines.json"
    monkeypatch.setattr(
        vibeforcer.lint._baseline,
        "_baseline_path",
        lambda: baseline_path,
    )
    first = Violation("demo-rule", "src/b.py", "B")
    second = Violation("demo-rule", "src/a.py", "A")

    save_baseline({"demo-rule": [first, second]})

    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert payload["rules"]["demo-rule"] == [second.stable_id, first.stable_id]


def test_load_baseline_reads_rule_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "baselines.json"
    baseline_path.write_text(
        json.dumps({"schema_version": 1, "rules": {"demo-rule": ["stable-id"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        vibeforcer.lint._baseline,
        "_baseline_path",
        lambda: baseline_path,
    )

    assert load_baseline() == {"demo-rule": {"stable-id"}}


def test_baseline_result_and_hash_helpers_are_deterministic() -> None:
    result = BaselineResult(
        new_violations=[],
        fixed_violations=["demo-rule|src/example.py|Example|detail"],
        current_count=0,
        baseline_count=1,
    )

    assert {
        "passed": result.passed,
        "fixed": result.fixed_violations,
        "hash8": content_hash("same content"),
        "hash12": content_hash("same content", length=12),
    } == {
        "passed": True,
        "fixed": ["demo-rule|src/example.py|Example|detail"],
        "hash8": content_hash("same content"),
        "hash12": content_hash("same content", length=12),
    }


@given(strategies.text(alphabet="-* abc/._", max_size=80))
def test_patch_added_content_never_includes_patch_headers(line: str) -> None:
    patch_blob = "\n".join(["+++ b/src/example.py", "*** Update File: x.py", f"+{line}"])

    assert extract_added_patch_content(patch_blob) == line


@given(strategies.lists(strategies.from_regex(r"src/[a-z]{1,8}\.py", fullmatch=True)))
def test_patch_candidate_paths_are_unique_in_first_seen_order(paths: list[str]) -> None:
    patch_blob = "\n".join(f"+++ b/{path}" for path in paths)
    expected = list(dict.fromkeys(paths))

    assert parse_patch_candidate_paths(patch_blob) == expected


@given(
    strategies.dictionaries(
        strategies.text(min_size=1),
        strategies.text(),
        min_size=1,
        max_size=3,
    )
)
def test_permission_request_allow_only_carries_updated_input(
    updated_input: dict[str, str],
) -> None:
    rendered = render_permission_request_output(
        "PermissionRequest",
        "allow",
        "approved",
        updated_input=updated_input,
    )

    assert rendered == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow", "updatedInput": updated_input},
        }
    }
