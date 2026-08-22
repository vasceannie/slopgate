from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.context import build_context
from slopgate.engine import evaluate_payload
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.adapters.opencode_projection.models import OPENCODE_TOOL_CONTRACT_VERSION
from slopgate.resources import resource_path
from slopgate.state import RepairRequiredPayload


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")
_CONTRACT_PATH = Path(__file__).parents[1] / "fixtures" / "opencode_tool_capability_contract.json"


@dataclass(frozen=True, slots=True)
class _CapabilityDecision:
    expected_blocked: bool
    python_blocked: bool
    plugin_blocked: bool
    detail: str


def contract_cases(path: Path) -> list[ObjectDict]:
    return [object_dict(item) for item in object_list(json.loads(path.read_text()))]


def capability_payload(repo: Path, case: ObjectDict) -> ObjectDict:
    return {
        "hook_event_name": "tool.execute.before",
        "tool_name": string_value(case.get("tool_name")) or "",
        "tool_input": object_dict(case.get("tool_input")),
        "cwd": str(repo),
        "worktree": str(repo),
        "session_id": "capability-contract",
        "call_id": string_value(case.get("id")) or "contract-call",
        "opencode_tool_contract_version": (
            string_value(case.get("contract_version"))
            or OPENCODE_TOOL_CONTRACT_VERSION
        ),
    }


def prepare_repair_state(payload: ObjectDict, repair_required: bool) -> None:
    if not repair_required:
        return
    context = build_context(OpenCodeAdapter().normalize_payload(payload))
    context.state.mark_repair_required(
        "contract-generation",
        RepairRequiredPayload(
            session_id="capability-contract",
            call_id="repair-source",
            rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
        ),
    )


def run_generated_plugin(
    tmp_path: Path,
    repo: Path,
    case: ObjectDict,
) -> subprocess.CompletedProcess[str]:
    plugin_path = tmp_path / "slopgate-plugin.ts"
    contract_version = (
        string_value(case.get("contract_version"))
        or OPENCODE_TOOL_CONTRACT_VERSION
    )
    template = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    template = template.replace(
        OPENCODE_TOOL_CONTRACT_VERSION,
        contract_version,
        1,
    )
    plugin_path.write_text(
        render_opencode_plugin(
            template,
            sys.executable,
            {"opencode_version": "1.18.21"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(_runner_source(plugin_path, repo, case), encoding="utf-8")
    env = dict(os.environ)
    env.pop("SLOPGATE_BIN", None)
    env["SLOPGATE_DAEMON_SOCKET"] = str(tmp_path / "no-daemon.sock")
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _runner_source(plugin_path: Path, repo: Path, case: ObjectDict) -> str:
    tool_name = string_value(case.get("tool_name")) or ""
    call_id = string_value(case.get("id")) or "contract-call"
    tool_input = object_dict(case.get("tool_input"))
    return f"""
import {{ EnforcerPlugin }} from {json.dumps(plugin_path.as_uri())}
const handlers = await EnforcerPlugin({{
  client: {{ app: {{ log: async () => {{}} }} }},
  directory: {json.dumps(str(repo))},
  worktree: {json.dumps(str(repo))},
}})
await handlers["tool.execute.before"](
  {{ tool: {json.dumps(tool_name)}, sessionID: "capability-contract", callID: {json.dumps(call_id)} }},
  {{ args: {json.dumps(tool_input)} }},
)
console.log("allowed")
"""


_CASES = tuple(
    pytest.param(case, id=string_value(case.get("id")) or "unnamed")
    for case in contract_cases(_CONTRACT_PATH)
)


def _prepare_repo(tmp_path: Path, case: ObjectDict) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    if case.get("source_mode") == "symlink":
        outside = tmp_path / "outside.py"
        outside.write_text("VALUE = 1\n", encoding="utf-8")
        source.symlink_to(outside)
    else:
        source.write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    return repo


def _evaluate_capability_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: ObjectDict,
) -> _CapabilityDecision:
    repo = _prepare_repo(tmp_path, case)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "slopgate-root"))
    payload = capability_payload(repo, case)
    prepare_repair_state(payload, case.get("repair_required") is True)
    python_result = evaluate_payload(payload, platform="opencode")
    plugin_result = run_generated_plugin(tmp_path, repo, case)
    return _CapabilityDecision(
        expected_blocked=case.get("expected") == "block",
        python_blocked=(
            python_result.output is not None
            and python_result.output.get("action") == "block"
        ),
        plugin_blocked=plugin_result.returncode != 0,
        detail=(
            f"python={python_result.output}, plugin={plugin_result.stderr}"
        ),
    )


@pytest.mark.parametrize("case", _CASES)
def test_python_and_generated_plugin_share_tool_capability_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: ObjectDict,
) -> None:
    decision = _evaluate_capability_case(tmp_path, monkeypatch, case)

    assert (decision.python_blocked, decision.plugin_blocked) == (
        decision.expected_blocked,
        decision.expected_blocked,
    ), (
        f"capability disagreement for {case.get('id')}: {decision.detail}"
    )
