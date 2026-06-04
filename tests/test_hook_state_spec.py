from __future__ import annotations
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from time import time
from typing import TypedDict
import pytest
from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.adapters import get_adapter
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult, RuleFinding, Severity
from slopgate.state import HookStateStore
from tests.support import BUNDLE_ROOT, assert_denied_by, assert_not_denied, finding_ids
_RESOURCES = BUNDLE_ROOT / "src" / "slopgate" / "resources"
class _SubprocessFinding(TypedDict):
    rule_id: str
    decision: str | None
    severity: str
    message: str | None
    metadata: ObjectDict
class _SubprocessResult(TypedDict):
    finding_ids: list[str]
    findings: list[_SubprocessFinding]
    output: ObjectDict | None
class _InspectableHookStateStore(HookStateStore):
    def full_read_key(self, session_id: str, path: str) -> str:
        return self._full_read_key(session_id, path)
    def save_state_for_test(self, state: Mapping[str, object]) -> None:
        self._save_state(state)
    @property
    def ttl_seconds(self) -> int:
        return self._TTL_SECONDS
    def load_state_for_test(self) -> ObjectDict:
        return object_dict(self._load_state())
def _normalize_subprocess_result(raw: object) -> _SubprocessResult:
    payload = object_dict(raw)
    raw_finding_ids = object_list(payload.get("finding_ids"))
    finding_ids_result = [item for item in raw_finding_ids if isinstance(item, str)]
    findings_result: list[_SubprocessFinding] = []
    for raw_finding in object_list(payload.get("findings")):
        finding = object_dict(raw_finding)
        rule_id = string_value(finding.get("rule_id"))
        severity = string_value(finding.get("severity"))
        if rule_id is None or severity is None:
            continue
        decision = string_value(finding.get("decision"))
        message = string_value(finding.get("message"))
        findings_result.append(
            {
                "rule_id": rule_id,
                "decision": decision,
                "severity": severity,
                "message": message,
                "metadata": object_dict(finding.get("metadata")),
            }
        )
    raw_output = payload.get("output")
    output = object_dict(raw_output) if raw_output is not None else None
    return {
        "finding_ids": finding_ids_result,
        "findings": findings_result,
        "output": output,
    }
def _config_with_enabled_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *rule_ids: str
) -> None:
    (tmp_path / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    raw = json.loads((_RESOURCES / "defaults.json").read_text(encoding="utf-8"))
    enabled = dict(raw.get("enabled_rules", {}))
    for rule_id in rule_ids:
        enabled[rule_id] = True
    raw["enabled_rules"] = enabled
    config_path = tmp_path / "spec-config.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
def _enable_thin_wrapper_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _config_with_enabled_rules(tmp_path, monkeypatch, "PY-CODE-013")
def _enable_loop_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _config_with_enabled_rules(tmp_path, monkeypatch, "PY-CODE-013", "PY-CODE-009")
def _ensure_enrolled(cwd: str) -> None:
    root = Path(cwd)
    marker = root / "slopgate.toml"
    if not marker.exists():
        marker.write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
def _read_payload(
    file_path: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    _ensure_enrolled(cwd)
    tool_input: dict[str, object] = {"file_path": file_path}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": tool_input,
    }
def _bash_payload(
    command: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    _ensure_enrolled(cwd)
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
def _grep_payload(
    query: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    _ensure_enrolled(cwd)
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Grep",
        "tool_input": {"query": query, "path": "src"},
    }
def _posttool_payload(
    *,
    cwd: Path,
    rel_path: str,
    code: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    _ensure_enrolled(str(cwd))
    target = cwd / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    return {
        "session_id": session_id,
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": rel_path, "content": code},
        "tool_response": {"filePath": rel_path, "success": True},
    }
_THIN_WRAPPER_CODE = "def get_all_users():\n    return UserRepository.find_all()\n"
def _thin_wrapper_payload(cwd: Path, session_id: str = "repeat-session") -> dict[str, object]:
    return _posttool_payload(
        cwd=cwd,
        rel_path="src/thin.py",
        code=_THIN_WRAPPER_CODE,
        session_id=session_id,
    )
def _evaluate_thin_wrapper_hit(cwd: Path, session_id: str = "repeat-session") -> EngineResult:
    return evaluate_payload(_thin_wrapper_payload(cwd, session_id))
def _evaluate_thin_wrapper_hits(cwd: Path, count: int, session_id: str = "repeat-session") -> list[EngineResult]:
    return [_evaluate_thin_wrapper_hit(cwd, session_id) for _ in range(count)]
def _run_thin_wrapper_subprocess_hit(
    cwd: Path, session_id: str = "repeat-session"
) -> _SubprocessResult:
    return _run_payload_in_subprocess(_thin_wrapper_payload(cwd, session_id))
def _require_subprocess_finding(
    rule_id: str, result: _SubprocessResult
) -> _SubprocessFinding:
    return next(item for item in result["findings"] if item["rule_id"] == rule_id)
def _repeat_tracking_repair_sequence(cwd: Path) -> tuple[EngineResult, EngineResult]:
    thin_wrapper = "def get_all_users():\n    return UserRepository.find_all()\n"
    repaired_code = (
        "def get_all_users():\n"
        "    users = UserRepository.find_all()\n"
        "    return users\n"
    )
    session_id = "repeat-session"
    rel_path = "src/thin.py"
    _ = evaluate_payload(
        _posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    _ = evaluate_payload(
        _posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    repaired = evaluate_payload(
        _posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=repaired_code,
            session_id=session_id,
        )
    )
    repeated_after_repair = evaluate_payload(
        _posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    return repaired, repeated_after_repair
def _python_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(BUNDLE_ROOT / "src")
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path if not current_pythonpath else src_path + os.pathsep + current_pythonpath
    )
    return env
def _run_payload_in_subprocess(
    payload: dict[str, object],
    *,
    platform: str = "claude",
) -> _SubprocessResult:
    """Run one hook evaluation in a fresh Python process.
    Slopgate hooks are invoked as subprocesses in production, so this helper keeps
    the spec honest about persistence requirements.
    """
    script = """
import json
import sys
from slopgate.engine import evaluate_payload
payload = json.loads(sys.argv[1])
platform = sys.argv[2]
result = evaluate_payload(payload, platform=platform)
print(json.dumps({
    "finding_ids": [f.rule_id for f in result.findings],
    "findings": [
        {
            "rule_id": f.rule_id,
            "decision": f.decision,
            "severity": f.severity.name,
            "message": f.message,
            "metadata": f.metadata,
        }
        for f in result.findings
    ],
    "output": result.output,
}, default=str))
""".strip()
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps(payload), platform],
        capture_output=True,
        text=True,
        check=True,
        env=_python_subprocess_env(),
    )
    return _normalize_subprocess_result(json.loads(completed.stdout))
def _start_full_read_record_subprocess(
    trace_dir: Path, session_id: str, file_path: Path
) -> subprocess.Popen[str]:
    script = """
import sys
from pathlib import Path
from slopgate.state import HookStateStore
store = HookStateStore(Path(sys.argv[1]))
store.record_full_read(sys.argv[2], sys.argv[3])
""".strip()
    return subprocess.Popen(
        [sys.executable, "-c", script, str(trace_dir), session_id, str(file_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_python_subprocess_env(),
    )
def _start_full_read_record_processes(
    trace_dir: Path, count: int
) -> tuple[list[Path], list[subprocess.Popen[str]]]:
    targets: list[Path] = []
    processes: list[subprocess.Popen[str]] = []
    for idx in range(count):
        target = trace_dir / f"module_{idx}.py"
        target.write_text(f"value = {idx}\n", encoding="utf-8")
        targets.append(target)
        processes.append(_start_full_read_record_subprocess(trace_dir, f"session-{idx}", target))
    return targets, processes
def _collect_process_failures(
    processes: list[subprocess.Popen[str]], timeout: int = 10
) -> tuple[list[str], list[tuple[int | None, str]]]:
    timed_out: list[str] = []
    failed: list[tuple[int | None, str]] = []
    for process in processes:
        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            timed_out.append(str(process.args))
        else:
            if process.returncode != 0:
                failed.append((process.returncode, stderr))
    return timed_out, failed
def _missing_full_read_records(
    store: _InspectableHookStateStore, targets: list[Path]
) -> list[str]:
    return [
        str(target)
        for idx, target in enumerate(targets)
        if not store.has_full_read(f"session-{idx}", str(target))
    ]
def _finding(result_rule_id: str, findings: list[RuleFinding]) -> RuleFinding | None:
    return next((item for item in findings if item.rule_id == result_rule_id), None)
def _require_finding(result_rule_id: str, findings: list[RuleFinding]) -> RuleFinding:
    finding = _finding(result_rule_id, findings)
    assert finding is not None, f"expected {result_rule_id} finding to be emitted"
    return finding
def _assert_repeat_counts(
    first_finding: RuleFinding,
    second_finding: RuleFinding,
    *,
    expected_first: int,
    expected_second: int,
) -> None:
    assert first_finding.metadata.get("repeat_count") == expected_first, (
        "first repeated-debt hit should initialize repeat_count"
    )
    assert second_finding.metadata.get("repeat_count") == expected_second, (
        "second repeated-debt hit should increment repeat_count"
    )
def _assert_loop_steering_metadata(
    first_finding: RuleFinding, second_finding: RuleFinding
) -> None:
    assert first_finding.metadata.get("failure_class") == "structural", (
        "loop-aware steering should classify thin-wrapper debt as structural"
    )
    assert second_finding.metadata.get("repeat_hit") is True, (
        "second matching hit should be marked as repeat_hit"
    )
    assert second_finding.additional_context and "Classify the failure first" in (
        second_finding.additional_context
    ), "repeat denial should instruct the agent to classify before retrying"
# Exported test support used by split test modules.
__all__ = ('BUNDLE_ROOT', 'EngineResult', 'HookStateStore', 'Mapping', 'ObjectDict', 'Path', 'RuleFinding', 'Severity', 'TypedDict', '_InspectableHookStateStore', '_RESOURCES', '_SubprocessFinding', '_SubprocessResult', '_THIN_WRAPPER_CODE', '_assert_loop_steering_metadata', '_assert_repeat_counts', '_bash_payload', '_collect_process_failures', '_config_with_enabled_rules', '_enable_loop_rules', '_enable_thin_wrapper_rule', '_ensure_enrolled', '_evaluate_thin_wrapper_hit', '_evaluate_thin_wrapper_hits', '_finding', '_grep_payload', '_missing_full_read_records', '_normalize_subprocess_result', '_posttool_payload', '_python_subprocess_env', '_read_payload', '_repeat_tracking_repair_sequence', '_require_finding', '_require_subprocess_finding', '_run_payload_in_subprocess', '_run_thin_wrapper_subprocess_hit', '_start_full_read_record_processes', '_start_full_read_record_subprocess', '_thin_wrapper_payload', 'assert_denied_by', 'assert_not_denied', 'evaluate_payload', 'finding_ids', 'get_adapter', 'json', 'object_dict', 'object_list', 'os', 'pytest', 'string_value', 'subprocess', 'sys', 'time')
