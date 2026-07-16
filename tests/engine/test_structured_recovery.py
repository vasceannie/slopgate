from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import time

import pytest

from slopgate._types import object_dict
from slopgate.cli import main
from slopgate.context import HookContext
from slopgate.engine import evaluate_payload
from slopgate.engine._retry.budget import (
    capture_repair_plan_signal,
    record_full_read_evidence,
)
from slopgate.state import (
    HookStateStore,
    RecoveryEvidenceDraft,
    RecoveryEvidenceRecord,
)
from tests.semantic_retry_support import (
    LONG_PARAMS_RULE,
    SESSION_ID,
    TARGET,
    configure_retry_test,
    full_read_payload,
    lock_retry,
    lock_retry_and_read,
    long_params_payload,
    record_unchanged_recovery,
    recorded_recovery,
    recovery_record_args,
    retry_context,
)
from tests.test_hook_state_spec import run_payload_in_subprocess
from tests.support import finding_ids


FIRST_DESIGN = "def build(a, b, c, d, e, f, g):\n    return a\n"
SECOND_DESIGN = "def build(a,b,c,d,e,f,g):\n    return b\n"
CHANGED_DESIGN = (
    "def build(one, two, three, four, five, six, seven):\n    return seven\n"
)
RECOVERY_FIELDS = {
    "target_paths",
    "locked_rules",
    "files_reread_after_lock",
    "violated_invariant",
    "previous_design_failure",
    "new_design",
    "verification",
    "created_at",
    "schema_version",
}


@dataclass(frozen=True, slots=True)
class RecoveryMutation:
    field: str
    value: int


RECOVERY_MUTATIONS = (
    RecoveryMutation("created_at", int(time()) - 3601),
    RecoveryMutation("schema_version", 999),
)


def test_budget_full_read_evidence_records_real_post_tool_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, trace_dir = configure_retry_test(tmp_path, monkeypatch)
    ctx, state = retry_context(full_read_payload(repo), trace_dir)

    record_full_read_evidence(ctx)

    assert state.retry_full_read_sequence(SESSION_ID, str(repo / TARGET)) == 1


def test_capture_repair_plan_signal_does_not_mutate_retry_state() -> None:
    assert capture_repair_plan_signal(object.__new__(HookContext)) is None


def test_recovery_record_requires_full_read_after_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    _ = evaluate_payload(full_read_payload(repo))
    lock_retry(repo, (FIRST_DESIGN, SECOND_DESIGN))

    exit_code = main(recovery_record_args(repo))

    assert exit_code == 2, "A read before the lock must not satisfy recovery proof"
    assert capsys.readouterr().err, (
        "Rejected recovery evidence should explain the boundary"
    )


def test_pre_tool_read_after_lock_is_not_successful_read_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry(repo, (FIRST_DESIGN, SECOND_DESIGN))
    _ = evaluate_payload(full_read_payload(repo, event_name="PreToolUse"))

    exit_code = main(recovery_record_args(repo))

    assert exit_code == 2, "A proposed read must not prove that the file was reread"
    assert capsys.readouterr().err, (
        "Rejected recovery should explain missing read proof"
    )


def test_partial_post_tool_read_after_lock_is_not_full_read_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry(repo, (FIRST_DESIGN, SECOND_DESIGN))
    payload = full_read_payload(repo)
    payload["tool_input"] = {"file_path": TARGET, "offset": 1, "limit": 1}
    _ = evaluate_payload(payload)

    exit_code = main(recovery_record_args(repo))

    assert exit_code == 2, "Partial post-lock reads must not prove recovery"
    assert capsys.readouterr().err, (
        "Rejected partial-read recovery should explain missing read proof"
    )


def test_recovery_record_persists_exact_privacy_safe_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = recorded_recovery(
        tmp_path, monkeypatch, capsys, (FIRST_DESIGN, SECOND_DESIGN)
    )
    repo = scenario.repo
    exit_code = 0
    state = scenario.state
    evidence_map = object_dict(state["recovery_evidence"])
    evidence = object_dict(evidence_map[scenario.evidence_key])

    assert exit_code == 0, "Complete structured recovery evidence should record"
    assert set(evidence) == RECOVERY_FIELDS, (
        "Persisted recovery evidence must use only the specified schema fields"
    )
    assert evidence["target_paths"] == [str((repo / TARGET).resolve())], (
        "Recovery evidence should derive normalized locked targets"
    )
    assert evidence["locked_rules"] == [LONG_PARAMS_RULE], (
        "Recovery evidence should derive currently locked rules"
    )
    assert evidence["files_reread_after_lock"] == [str((repo / TARGET).resolve())], (
        "Recovery evidence should persist actual post-lock full reads"
    )
    serialized = json.dumps(evidence)
    assert FIRST_DESIGN not in serialized and SECOND_DESIGN not in serialized, (
        "Recovery state must not persist prompt, source, or tool-input content"
    )


def test_state_store_records_public_recovery_evidence_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry_and_read(repo, (FIRST_DESIGN, SECOND_DESIGN))
    draft = RecoveryEvidenceDraft(
        session_id="semantic-retry-session",
        repo_root=str(repo.resolve()),
        violated_invariant="public call sites must not receive seven parameters",
        previous_design_failure="kept adding positional parameters",
        new_design="replace the parameters with a typed request value",
        verification="run focused retry lifecycle tests",
    )

    record = HookStateStore(trace_dir).record_recovery_evidence(draft)

    assert isinstance(record, RecoveryEvidenceRecord), (
        "State recovery should return the public recovery evidence record model"
    )
    assert record.target_paths == (str((repo / TARGET).resolve()),), (
        "Recovery record should derive targets from active semantic locks"
    )


@pytest.mark.parametrize(
    "mutation",
    RECOVERY_MUTATIONS,
    ids=("expired", "schema_mismatch"),
)
def test_expired_or_schema_invalid_recovery_does_not_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: RecoveryMutation,
) -> None:
    scenario = recorded_recovery(
        tmp_path, monkeypatch, capsys, (FIRST_DESIGN, SECOND_DESIGN)
    )
    third = scenario.retry_after_mutation(
        mutation.field, mutation.value, CHANGED_DESIGN
    )

    assert "RETRY-BUDGET-001" in finding_ids(third), (
        "Expired or schema-invalid recovery evidence must not unlock"
    )


def test_materially_unchanged_design_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry_and_read(repo, (FIRST_DESIGN, SECOND_DESIGN))
    exit_code = record_unchanged_recovery(repo, capsys)
    third = evaluate_payload(long_params_payload(repo, CHANGED_DESIGN))

    assert exit_code == 2, "Cosmetic design text changes should be rejected"
    assert "RETRY-BUDGET-001" in finding_ids(third), (
        "Rejected recovery evidence must leave the semantic lock active"
    )


def test_wrong_session_cannot_record_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry_and_read(repo, (FIRST_DESIGN, SECOND_DESIGN))
    wrong_session = main(recovery_record_args(repo, session_id="other-session"))
    _ = capsys.readouterr()

    assert wrong_session == 2, "Recovery must match the normalized locked session"


def test_wrong_repo_cannot_record_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry_and_read(repo, (FIRST_DESIGN, SECOND_DESIGN))
    other_repo = tmp_path / "other-repo"
    other_repo.mkdir()
    wrong_repo_args = recovery_record_args(repo)
    wrong_repo_args[wrong_repo_args.index("--cwd") + 1] = str(other_repo)

    wrong_repo = main(wrong_repo_args)
    _ = capsys.readouterr()

    assert wrong_repo == 2, "Recovery must match the normalized locked repository"


def test_valid_recovery_consumes_once_and_survives_subprocess_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = recorded_recovery(
        tmp_path, monkeypatch, capsys, (FIRST_DESIGN, SECOND_DESIGN)
    )
    retry = run_payload_in_subprocess(
        long_params_payload(scenario.repo, CHANGED_DESIGN)
    )
    after = scenario.reload_state()

    assert "RETRY-BUDGET-001" not in retry["finding_ids"], (
        "A valid changed-design retry should unlock across hook subprocesses"
    )
    assert object_dict(after["recovery_evidence"]) == {}, (
        "Successful unlock should consume structured recovery evidence"
    )
