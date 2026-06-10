"""Subprocess helpers for hook state spec tests."""

from __future__ import annotations

__all__ = [
    "Path",
    "TypedDict",
    "ObjectDict",
    "object_dict",
    "object_list",
    "string_value",
    "RuleFinding",
    "HookStateStore",
    "BUNDLE_ROOT",
    "_SubprocessFinding",
    "_SubprocessResult",
    "_normalize_subprocess_result",
    "_python_subprocess_env",
    "run_payload_in_subprocess",
    "_start_full_read_record_subprocess",
    "start_full_read_record_processes",
    "collect_process_failures",
    "missing_full_read_records",
    "finding",
    "require_finding",
    "assert_repeat_counts",
    "assert_loop_steering_metadata",
]




import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.models import RuleFinding
from slopgate.state import HookStateStore
from tests.support import BUNDLE_ROOT


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


def _python_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(BUNDLE_ROOT / "src")
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path
        if not current_pythonpath
        else src_path + os.pathsep + current_pythonpath
    )
    return env


def run_payload_in_subprocess(
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


def start_full_read_record_processes(
    trace_dir: Path, count: int
) -> tuple[list[Path], list[subprocess.Popen[str]]]:
    targets: list[Path] = []
    processes: list[subprocess.Popen[str]] = []
    for idx in range(count):
        target = trace_dir / f"module_{idx}.py"
        target.write_text(f"value = {idx}\n", encoding="utf-8")
        targets.append(target)
        processes.append(
            _start_full_read_record_subprocess(trace_dir, f"session-{idx}", target)
        )
    return targets, processes


def collect_process_failures(
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


def missing_full_read_records(store: HookStateStore, targets: list[Path]) -> list[str]:
    return [
        str(target)
        for idx, target in enumerate(targets)
        if not store.has_full_read(f"session-{idx}", str(target))
    ]


def finding(result_rule_id: str, findings: list[RuleFinding]) -> RuleFinding | None:
    return next((item for item in findings if item.rule_id == result_rule_id), None)


def require_finding(result_rule_id: str, findings: list[RuleFinding]) -> RuleFinding:
    matched = finding(result_rule_id, findings)
    assert matched is not None, f"expected {result_rule_id} finding to be emitted"
    return matched


def assert_repeat_counts(
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


def assert_loop_steering_metadata(
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
