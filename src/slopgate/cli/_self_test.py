"""Self-test smoke command implementation."""

from __future__ import annotations

import argparse
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from slopgate._types import ObjectDict
from slopgate.constants import SELFTEST_SEPARATOR_WIDTH, SESSION_ID
from slopgate.models import EngineResult

PlatformName = str
SelfTestCase = tuple[str, str, str, ObjectDict, PlatformName, bool, str]


def _run_one_test(
    evaluate_payload: Callable[[Mapping[str, object], PlatformName], EngineResult],
    case: SelfTestCase,
) -> str:
    label, event, tool, tool_input, platform, expect_deny, cwd = case
    payload = {
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": cwd,
        SESSION_ID: f"self-test-{platform}-{label}",
    }
    result = evaluate_payload(payload, platform)
    deny_count = sum(1 for f in result.findings if f.decision in {"deny", "block"})
    passed = (deny_count > 0) if expect_deny else (deny_count == 0)
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {label} ({deny_count} finding(s))")
    return status


def _self_test_cases(strict_cwd: str, outside_cwd: str) -> list[SelfTestCase]:
    env_path = str(Path.home() / ".env")
    noverify: ObjectDict = {"command": "git commit --no-verify -m 'test'"}
    return [
        (
            "git --no-verify → deny",
            "PreToolUse",
            "Bash",
            noverify,
            "claude",
            True,
            strict_cwd,
        ),
        (
            ".env write → deny",
            "PreToolUse",
            "Write",
            {"file_path": env_path, "content": "SECRET=***"},
            "claude",
            True,
            outside_cwd,
        ),
        (
            "echo hello → allow",
            "PreToolUse",
            "Bash",
            {"command": "echo hello"},
            "claude",
            False,
            strict_cwd,
        ),
        (
            "codex adapter → deny",
            "PreToolUse",
            "Bash",
            noverify,
            "codex",
            True,
            strict_cwd,
        ),
        (
            "opencode adapter → deny",
            "tool.execute.before",
            "bash",
            noverify,
            "opencode",
            True,
            strict_cwd,
        ),
    ]


def cmd_test(_args: argparse.Namespace) -> int:
    from slopgate.engine import evaluate_payload

    print("slopgate self-test")
    print("=" * SELFTEST_SEPARATOR_WIDTH)
    with tempfile.TemporaryDirectory(prefix="slopgate-self-test-") as tmpdir:
        strict_repo = Path(tmpdir)
        (strict_repo / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n",
            encoding="utf-8",
        )
        cases = _self_test_cases(str(strict_repo), tempfile.gettempdir())
        statuses = [_run_one_test(evaluate_payload, case) for case in cases]
    all_pass = all(status == "PASS" for status in statuses)
    print()
    print("All tests passed." if all_pass else "SOME TESTS FAILED.")
    return 0 if all_pass else 1
