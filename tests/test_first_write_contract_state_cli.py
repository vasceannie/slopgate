from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

from hypothesis import given, settings, strategies
import pytest

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.cli import main
from slopgate.engine import evaluate_payload
from slopgate.state import (
    FirstWriteContractCheck,
    FirstWriteContractDraft,
    FirstWriteContractRecord,
    FirstWriteContractStateMixin,
    HookStateStore,
    normalize_contract_operation,
    normalize_contract_target,
)
from tests.first_write_contract_support import (
    RULE_ID,
    contract_record_args,
    configure_contract_test,
    edit_payload,
)


SCHEMA_VERSION = 1
PATH_SEGMENT = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True)
OPERATION_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ- _",
    min_size=1,
    max_size=40,
)


@dataclass(frozen=True, slots=True)
class _RecordedContract:
    exit_code: int
    output: ObjectDict
    entry: ObjectDict
    before: int


def _record_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _RecordedContract:
    repo, trace_dir = configure_contract_test(tmp_path, monkeypatch)
    before = int(time())
    exit_code = main(contract_record_args(repo, session_id=" session-a "))
    output = object_dict(json.loads(capsys.readouterr().out))
    state = object_dict(json.loads((trace_dir / "hook-state.json").read_text()))
    contracts = object_dict(state.get("first_write_contracts"))
    entry = object_dict(next(iter(contracts.values())))
    return _RecordedContract(exit_code, output, entry, before)


def test_contract_record_cli_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorded = _record_contract(tmp_path, monkeypatch, capsys)

    assert recorded.exit_code == 0, "Complete contract recording should succeed"
    assert recorded.output["status"] == "recorded", (
        "CLI should report a recorded contract"
    )


def test_contract_record_cli_persists_normalized_privacy_safe_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    recorded = _record_contract(tmp_path, monkeypatch, capsys)

    entry = recorded.entry
    assert entry["schema_version"] == SCHEMA_VERSION, "State should pin the schema"
    assert entry["operation"] == "edit", "State should normalize the operation"
    assert entry["target"] == str((repo / "src/app.py").resolve()), (
        "State should normalize the target against the supplied cwd"
    )
    assert "content" not in entry, "Contract state must not persist source content"


def test_contract_record_cli_persists_timestamp_and_risk_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorded = _record_contract(tmp_path, monkeypatch, capsys)

    timestamp = recorded.entry["timestamp"]
    predicted_risks = object_list(recorded.entry["predicted_risks"])
    assert isinstance(timestamp, int) and timestamp >= recorded.before, (
        "State should timestamp the contract"
    )
    assert len(predicted_risks) == 3, "State should retain 3-5 risks"


@pytest.mark.parametrize(
    "risk_count",
    (2, 6),
    ids=("too_few", "too_many"),
)
def test_contract_record_cli_rejects_risk_counts_outside_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    risk_count: int,
) -> None:
    repo, trace_dir = configure_contract_test(tmp_path, monkeypatch)
    risks = tuple(f"risk-{index}" for index in range(risk_count))

    exit_code = main(contract_record_args(repo, risks=risks))

    captured = capsys.readouterr()
    assert exit_code == 2, "Invalid risk counts should fail contract recording"
    assert captured.err, "Invalid contract input should explain the boundary"
    assert not (trace_dir / "hook-state.json").exists(), (
        "Invalid contract input should not create persisted state"
    )


def test_normalized_session_target_and_operation_authorize_recorded_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch)
    args = contract_record_args(
        repo, target="src/../src/app.py", session_id=" session-a "
    )
    assert main(args) == 0, "Complete normalized contract should record"
    _ = capsys.readouterr()

    result = evaluate_payload(edit_payload(repo), platform="claude")

    assert all(item.rule_id != RULE_ID for item in result.findings), (
        "Normalized session, target, and operation should authorize the mutation"
    )


@settings(max_examples=25)
@given(segment=PATH_SEGMENT)
def test_normalize_contract_target_resolves_relative_paths_property(
    segment: str,
) -> None:
    with TemporaryDirectory() as raw_cwd:
        cwd = Path(raw_cwd)

        normalized = normalize_contract_target(f"src/../{segment}.py", cwd)

    assert normalized == str((cwd / f"{segment}.py").resolve()), (
        "Contract target normalization should canonicalize relative paths"
    )


@settings(max_examples=25)
@given(operation=OPERATION_TEXT)
def test_normalize_contract_operation_is_idempotent_property(
    operation: str,
) -> None:
    normalized = normalize_contract_operation(operation)

    assert normalize_contract_operation(normalized) == normalized, (
        "Contract operation normalization should be idempotent"
    )


def test_state_store_records_public_first_write_contract_models(
    tmp_path: Path,
) -> None:
    target = str((tmp_path / "src/app.py").resolve())
    store = HookStateStore(tmp_path / "trace")
    draft = FirstWriteContractDraft(
        session_id="session-a",
        target=target,
        operation="Edit",
        reuse_convention="reuse existing state facade",
        stable_behavior_api="preserve hook output shape",
        predicted_risks=("state drift", "path normalization", "stale contract"),
        design_response="record normalized privacy-safe state",
        focused_verification="run contract CLI tests",
    )

    record = store.record_first_write_contract(draft)
    checks = store.authorize_first_write_contracts("session-a", [target], "Edit")

    assert isinstance(store, FirstWriteContractStateMixin), (
        "HookStateStore should expose the first-write state behavior"
    )
    assert isinstance(record, FirstWriteContractRecord), (
        "Recording should return the public first-write record model"
    )
    assert isinstance(checks[0], FirstWriteContractCheck), (
        "Authorization should return the public first-write check model"
    )
    assert checks[0].complete, "A complete public draft should authorize"


def _write_contract_state(repo: Path, trace_dir: Path, mutation: str) -> None:
    state: ObjectDict = {"full_reads": {}}
    if mutation != "legacy":
        main(contract_record_args(repo))
        state = object_dict(json.loads((trace_dir / "hook-state.json").read_text()))
        contracts = object_dict(state.get("first_write_contracts"))
        key = next(iter(contracts))
        entry = object_dict(contracts[key])
        if mutation == "expired":
            entry["timestamp"] = int(time()) - 3601
        else:
            entry["schema_version"] = SCHEMA_VERSION + 1
        contracts[key] = entry
        state["first_write_contracts"] = contracts
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "hook-state.json").write_text(json.dumps(state), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    (
        ("legacy", "missing"),
        ("expired", "expired"),
        ("schema", "schema_version"),
    ),
    ids=("legacy_state", "expired_contract", "schema_mismatch"),
)
def test_legacy_expired_and_schema_state_are_deterministically_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_status: str,
) -> None:
    repo, trace_dir = configure_contract_test(tmp_path, monkeypatch, action="context")
    _write_contract_state(repo, trace_dir, mutation)

    result = evaluate_payload(edit_payload(repo), platform="claude")

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    assert finding.metadata["contract_status"] == expected_status, (
        "Legacy, expired, and schema-invalid state should have stable status metadata"
    )
