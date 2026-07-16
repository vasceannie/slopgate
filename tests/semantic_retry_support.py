"""Builders for semantic retry and recovery lifecycle tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict
from slopgate.cli import main
from slopgate.config import load_config
from slopgate.context import HookContext
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload


LONG_PARAMS_RULE = "PY-CODE-009"
SESSION_ID = "semantic-retry-session"
TARGET = "src/api.py"


def retry_context(
    payload: dict[str, object], trace_dir: Path
) -> tuple[HookContext, HookStateStore]:
    config = load_config()
    state = HookStateStore(trace_dir)
    return (
        HookContext(
            payload=HookPayload(payload, config),
            config=config,
            trace=TraceWriter(trace_dir),
            state=state,
        ),
        state,
    )


@dataclass(frozen=True, slots=True)
class RetryPayloadCase:
    target: str = TARGET
    session_id: str = SESSION_ID
    event_name: str = "PreToolUse"
    tool_name: str = "Write"


@dataclass(frozen=True, slots=True)
class PathlessOperationCase:
    tool_name: str
    tool_input: dict[str, object]
    expected_category: str


@dataclass(frozen=True, slots=True)
class RecordedRecovery:
    repo: Path
    trace_dir: Path
    state: ObjectDict
    evidence_key: str

    def reload_state(self) -> ObjectDict:
        return object_dict(
            json.loads((self.trace_dir / "hook-state.json").read_text(encoding="utf-8"))
        )

    def retry_after_mutation(
        self, field: str, value: int, content: str
    ) -> EngineResult:
        evidence_map = object_dict(self.state["recovery_evidence"])
        entry = object_dict(evidence_map[self.evidence_key])
        entry[field] = value
        evidence_map[self.evidence_key] = entry
        self.state["recovery_evidence"] = evidence_map
        (self.trace_dir / "hook-state.json").write_text(
            json.dumps(self.state), encoding="utf-8"
        )
        return evaluate_payload(long_params_payload(self.repo, content))


def configure_retry_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    retry_action: str | None = None,
    retry_enabled: bool = True,
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    trace_dir = tmp_path / "trace"
    config_path = tmp_path / "config.json"
    config: dict[str, object] = {
        "trace_dir": str(trace_dir),
        "enabled_rules": {
            LONG_PARAMS_RULE: True,
            "RETRY-BUDGET-001": retry_enabled,
        },
    }
    if retry_action is not None:
        config["rule_surfaces"] = {
            "RETRY-BUDGET-001": {"hook": {"action": retry_action}}
        }
    config_path.write_text(
        json.dumps(config),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    return repo, trace_dir


def long_params_payload(
    repo: Path, content: str, case: RetryPayloadCase = RetryPayloadCase()
) -> dict[str, object]:
    return {
        "session_id": case.session_id,
        "cwd": str(repo),
        "hook_event_name": case.event_name,
        "tool_name": case.tool_name,
        "tool_input": {"file_path": case.target, "content": content},
    }


def evaluate_retry_designs(
    repo: Path,
    *designs: str,
    case: RetryPayloadCase = RetryPayloadCase(),
) -> list[EngineResult]:
    return [
        evaluate_payload(long_params_payload(repo, design, case)) for design in designs
    ]


def lock_retry_and_read(repo: Path, designs: tuple[str, str]) -> None:
    lock_retry(repo, designs)
    _ = evaluate_payload(full_read_payload(repo))


def lock_retry(repo: Path, designs: tuple[str, str]) -> None:
    _ = evaluate_retry_designs(repo, *designs)


def record_unchanged_recovery(repo: Path, capsys: pytest.CaptureFixture[str]) -> int:
    args = recovery_record_args(repo)
    previous_index = args.index("--previous-design-failure") + 1
    new_index = args.index("--new-design") + 1
    args[new_index] = args[previous_index].upper()
    exit_code = main(args)
    _ = capsys.readouterr()
    return exit_code


def recorded_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    designs: tuple[str, str],
) -> RecordedRecovery:
    repo, trace_dir = configure_retry_test(tmp_path, monkeypatch)
    lock_retry_and_read(repo, designs)
    exit_code = main(recovery_record_args(repo))
    _ = capsys.readouterr()
    if exit_code != 0:
        raise AssertionError("Valid recovery evidence should record")
    state = object_dict(
        json.loads((trace_dir / "hook-state.json").read_text(encoding="utf-8"))
    )
    evidence_key = next(iter(object_dict(state["recovery_evidence"])))
    return RecordedRecovery(repo, trace_dir, state, evidence_key)


def full_read_payload(repo: Path, event_name: str = "PostToolUse") -> dict[str, object]:
    path = repo / TARGET
    path.write_text("VALUE = 1\n", encoding="utf-8")
    return {
        "session_id": SESSION_ID,
        "cwd": str(repo),
        "hook_event_name": event_name,
        "tool_name": "Read",
        "tool_input": {"file_path": TARGET},
    }


def recovery_record_args(repo: Path, session_id: str = SESSION_ID) -> list[str]:
    return [
        "recovery",
        "record",
        "--session-id",
        session_id,
        "--violated-invariant",
        "public call sites must not receive a seven-parameter function",
        "--previous-design-failure",
        "kept adding positional parameters to the same function",
        "--new-design",
        "replace the positional group with a typed request value",
        "--verification",
        "run the focused retry lifecycle tests",
        "--cwd",
        str(repo),
    ]
