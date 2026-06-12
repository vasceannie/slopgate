from __future__ import annotations
from pytest import MonkeyPatch, CaptureFixture
import argparse
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from tests.test_adapters import ClaudeAdapter, RuleFinding, Severity, pytest
from slopgate.cli.commands import cmd_handle
from slopgate.models import EngineResult


TEAM_BLOCK_TITLE = "quality gate"
TEAM_BLOCK_MESSAGE = "repair the task before reporting completion"


@dataclass(frozen=True, slots=True)
class CmdHandleCase:
    event_name: str
    findings: Sequence[RuleFinding]
    output: dict[str, object] | None = None


def _run_cmd_handle(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    case: CmdHandleCase,
) -> tuple[int, str, str]:
    def fake_evaluate_payload(
        payload: object, platform: str = "claude"
    ) -> EngineResult:
        if platform != "claude":
            pytest.fail(f"unexpected platform: {platform}")
        return EngineResult(
            event_name=case.event_name,
            findings=list(case.findings),
            output=case.output,
        )

    import slopgate.engine

    monkeypatch.setattr(slopgate.engine, "evaluate_payload", fake_evaluate_payload)
    payload = {"hook_event_name": case.event_name, "cwd": "/tmp"}
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps(payload)),
    )
    exit_code = cmd_handle(argparse.Namespace(platform="claude"))
    captured = capsys.readouterr()
    return (exit_code, captured.out, captured.err)


@pytest.mark.parametrize("event_name", ["TaskCompleted", "TeammateIdle"])
def test_claude_team_event_blocks_do_not_render_continue_false(event_name: str) -> None:
    adapter = ClaudeAdapter()
    output = adapter.render_output(
        event_name,
        [
            RuleFinding(
                rule_id="TEAM-001",
                title=TEAM_BLOCK_TITLE,
                severity=Severity.HIGH,
                decision="block",
                message=TEAM_BLOCK_MESSAGE,
            )
        ],
        decision="block",
        context=None,
        updated_input={},
    )
    message = (
        f"{event_name} quality gates must rely on Claude's retry contract "
        "(exit 2 + stderr), not JSON continue:false teammate termination"
    )
    assert output is None, message


@pytest.mark.parametrize("event_name", ["TaskCompleted", "TeammateIdle"])
def test_cmd_handle_claude_team_event_block_exits_2_with_feedback(
    event_name: str, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    exit_code, stdout, stderr = _run_cmd_handle(
        monkeypatch,
        capsys,
        CmdHandleCase(
            event_name=event_name,
            findings=[
                RuleFinding(
                    rule_id="TEAM-002",
                    title=TEAM_BLOCK_TITLE,
                    severity=Severity.HIGH,
                    decision="block",
                    message=TEAM_BLOCK_MESSAGE,
                )
            ],
        ),
    )
    assert exit_code == 2, "Claude teammate retry block should use exit code 2"
    assert stdout == "", "Claude retry feedback must not emit stdout JSON"
    assert "TEAM-002" in stderr, "stderr feedback should include the blocking rule id"
    assert "repair the task" in stderr, "stderr feedback should explain the repair"
    assert "continue" not in stderr, "stderr must not teach continue:false termination"


def test_cmd_handle_claude_stop_block_still_uses_json_stdout(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    output: dict[str, object] = {
        "decision": "block",
        "reason": "[STOP-001 | HIGH] unfinished work",
    }
    exit_code, stdout, stderr = _run_cmd_handle(
        monkeypatch,
        capsys,
        CmdHandleCase(
            event_name="Stop",
            findings=[
                RuleFinding(
                    rule_id="STOP-001",
                    title=TEAM_BLOCK_TITLE,
                    severity=Severity.HIGH,
                    decision="block",
                    message=TEAM_BLOCK_MESSAGE,
                )
            ],
            output=output,
        ),
    )
    assert exit_code == 0, "Stop blocking should stay on Claude JSON output contract"
    assert json.loads(stdout) == output, "Stop output should pass through unchanged"
    assert stderr == "", "Stop JSON contract should not emit stderr feedback"
