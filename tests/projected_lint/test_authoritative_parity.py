from __future__ import annotations

from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from slopgate.models import RuleFinding
from slopgate.rules.projected_lint.parity import (
    ProjectionParitySnapshot,
    pop_parity_snapshot,
    record_parity_snapshot,
)
from tests.projected_lint.support import (
    BAD_TEST,
    RULE_ID,
    WriteCase,
    configure_rollout,
    materialize_projected_file,
    write_payload,
)


def test_post_edit_lint_reports_matching_projected_parity_metadata(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch)
    authoritative = _authoritative_lint_after_projection(projected_repo)

    parity = object_dict(authoritative.metadata["projected_lint_parity"])
    assert parity["projected_rule_id"] == RULE_ID, (
        "Parity should identify projected lint"
    )
    assert parity["status"] == "match", (
        "Projected and authoritative findings should match"
    )
    assert parity["authority"] == "post_edit", (
        "Post-edit lint must remain authoritative"
    )


def _authoritative_lint_after_projection(projected_repo: Path) -> RuleFinding:
    payload = write_payload(
        projected_repo, BAD_TEST, WriteCase(target="tests/test_app.py")
    )
    _ = evaluate_payload(payload, platform="claude")
    materialize_projected_file(projected_repo, "tests/test_app.py", BAD_TEST)
    payload["hook_event_name"] = "PostToolUse"

    result = evaluate_payload(payload, platform="claude")

    return next(item for item in result.findings if item.rule_id == "QUALITY-LINT-001")


def test_post_edit_lint_remains_authoritative_when_projection_disabled(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, enabled=False)
    target = projected_repo / "tests/test_app.py"
    target.parent.mkdir(parents=True)
    target.write_text(BAD_TEST, encoding="utf-8")
    payload = write_payload(
        projected_repo,
        BAD_TEST,
        WriteCase(event="PostToolUse", target="tests/test_app.py"),
    )

    result = evaluate_payload(payload, platform="claude")

    authoritative = next(
        item for item in result.findings if item.rule_id == "QUALITY-LINT-001"
    )
    assert authoritative.metadata["paths"] == ["tests/test_app.py"], (
        "Disabling projection must not disable authoritative post-edit lint"
    )


def test_parity_snapshot_round_trips_authoritative_collector_ids(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    paths = ["tests/test_app.py"]
    projected_ids = {"conditional-assertion": ["tests/test_app.py:branch"]}
    authoritative_ids = {"conditional-assertion": ["tests/test_app.py:branch"]}

    record_parity_snapshot(
        trace_dir,
        ProjectionParitySnapshot(
            session_id="session-a",
            paths=paths,
            collector_ids=projected_ids,
            projection_digest="digest-a",
        ),
    )
    parity = pop_parity_snapshot(trace_dir, "session-a", paths, authoritative_ids)

    assert parity is not None, "Recorded parity should be consumed once"
    assert parity["status"] == "match", (
        "Matching projected and authoritative collector ids should round-trip"
    )
