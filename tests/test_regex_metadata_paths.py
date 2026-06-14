"""Regression tests for canonical regex finding path metadata."""

from __future__ import annotations

from pathlib import Path

from slopgate.config import load_config
from slopgate.constants import METADATA_PATH
from slopgate.context import HookContext
from slopgate.engine import evaluate_payload
from slopgate.models import RegexRuleConfig
from slopgate.rules.regex_rule import RegexRule
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload

from tests.support import BUNDLE_ROOT


def regex_context(tmp_path: Path, payload: dict[str, object]) -> HookContext:
    config = load_config(tmp_path, ensure_enrollment=False, ensure_trace=False)
    trace = TraceWriter(tmp_path / ".slopgate" / "trace")
    return HookContext(
        payload=HookPayload(payload, config),
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def write_payload(file_path: str, content: str) -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(BUNDLE_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def test_content_target_finding_records_canonical_metadata_path(
    tmp_path: Path,
) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="CONTENT-PATH-TEST",
            title="Content path test",
            target="content",
            patterns=["danger_call"],
            events=["PreToolUse"],
            message="{rule_id}:{path}",
        )
    )
    ctx = regex_context(tmp_path, write_payload("src/app.py", "danger_call()\n"))

    findings = rule.evaluate(ctx)

    assert len(findings) == 1, "content target should produce one finding"
    assert findings[0].metadata == {
        "target": "content",
        "hits": ["src/app.py"],
        METADATA_PATH: "src/app.py",
    }


def test_content_target_finding_does_not_promote_patch_sentinel_path(
    tmp_path: Path,
) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="CONTENT-PATCH-SENTINEL-TEST",
            title="Content patch sentinel test",
            target="content",
            patterns=["danger_call"],
            events=["PreToolUse"],
            message="{rule_id}:{path}",
        )
    )
    ctx = regex_context(
        tmp_path,
        {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"patch": "danger_call()\n"},
        },
    )

    findings = rule.evaluate(ctx)

    assert len(findings) == 1, "patch fallback content should produce one finding"
    assert findings[0].metadata == {
        "target": "content",
        "hits": ["patch.diff"],
    }


def test_path_target_finding_records_canonical_metadata_path(tmp_path: Path) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="PATH-PATH-TEST",
            title="Path path test",
            target=METADATA_PATH,
            patterns=[r"src/app\.py"],
            events=["PreToolUse"],
            message="{rule_id}:{path}",
        )
    )
    ctx = regex_context(tmp_path, write_payload("src/app.py", "x = 1\n"))

    findings = rule.evaluate(ctx)

    assert len(findings) == 1, "path target should produce one finding"
    assert findings[0].metadata == {
        "target": METADATA_PATH,
        "hits": ["src/app.py"],
        METADATA_PATH: "src/app.py",
    }


def test_command_target_finding_does_not_fabricate_metadata_path(
    tmp_path: Path,
) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="COMMAND-PATH-TEST",
            title="Command path test",
            target="command",
            patterns=[r"set \+e"],
            events=["PreToolUse"],
            message="{rule_id}:{matched_paths}",
        )
    )
    ctx = regex_context(
        tmp_path,
        {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "set +e && make build"},
        },
    )

    findings = rule.evaluate(ctx)

    assert len(findings) == 1, "command target should produce one finding"
    assert findings[0].metadata == {"target": "command", "hits": []}


def test_prompt_target_finding_does_not_fabricate_metadata_path(
    tmp_path: Path,
) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="PROMPT-PATH-TEST",
            title="Prompt path test",
            target="prompt",
            patterns=["avoid mystery paths"],
            events=["UserPromptSubmit"],
            message="{rule_id}:{matched_paths}",
        )
    )
    ctx = regex_context(
        tmp_path,
        {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Please avoid mystery paths in this response.",
        },
    )

    findings = rule.evaluate(ctx)

    assert len(findings) == 1, "prompt target should produce one finding"
    assert findings[0].metadata == {"target": "prompt", "hits": []}


def test_py_test_002_content_finding_records_real_metadata_path() -> None:
    test_wait = "time." + "sleep(1)\n"
    result = evaluate_payload(
        write_payload(
            "tests/test_app.py",
            "import time\n\ndef test_waits():\n    " + test_wait,
        )
    )
    finding = next(item for item in result.findings if item.rule_id == "PY-TEST-002")

    assert finding.decision == "deny", "PY-TEST-002 should still deny test smells"
    assert finding.metadata.get(METADATA_PATH) == "tests/test_app.py", (
        "PY-TEST-002 should route retries to the real test path"
    )
    assert finding.metadata.get("hits") == ["tests/test_app.py"], (
        "PY-TEST-002 should keep the matched path list"
    )


def test_py_quality_006_content_finding_records_real_metadata_path() -> None:
    content = (
        "import "
        + "logging\n\n"
        + "def load_user():\n"
        + "    try:\n"
        + "        return fetch_user()\n"
        + "    except "
        + "Exception:\n"
        + "        logging"
        + ".exception('lookup failed')\n"
        + "        return "
        + "None\n"
    )
    result = evaluate_payload(write_payload("src/app.py", content))
    finding = next(item for item in result.findings if item.rule_id == "PY-QUALITY-006")

    assert finding.decision == "deny", "PY-QUALITY-006 should still deny silent None"
    assert finding.metadata.get(METADATA_PATH) == "src/app.py", (
        "PY-QUALITY-006 should route retries to the real source path"
    )
    assert finding.metadata.get("hits") == ["src/app.py"], (
        "PY-QUALITY-006 should keep the matched path list"
    )


def test_py_quality_009_content_finding_records_real_metadata_path() -> None:
    runtime_path = "/" + "tmp/" + "slopgate_runtime_config"
    result = evaluate_payload(
        write_payload("src/app.py", f"CONFIG_PATH = {runtime_path!r}\n")
    )
    finding = next(item for item in result.findings if item.rule_id == "PY-QUALITY-009")

    assert finding.decision == "deny", "PY-QUALITY-009 should still deny paths"
    assert finding.metadata.get(METADATA_PATH) == "src/app.py", (
        "PY-QUALITY-009 should route retries to the real source path"
    )
    assert finding.metadata.get("hits") == ["src/app.py"], (
        "PY-QUALITY-009 should keep the matched path list"
    )


def test_py_quality_010_content_finding_records_real_metadata_path() -> None:
    large_literal = "10" + "00"
    result = evaluate_payload(
        write_payload(
            "src/app.py", f"def is_large(value):\n    return value > {large_literal}\n"
        )
    )
    finding = next(item for item in result.findings if item.rule_id == "PY-QUALITY-010")

    assert finding.decision == "deny", "PY-QUALITY-010 should still deny literals"
    assert finding.metadata.get(METADATA_PATH) == "src/app.py", (
        "PY-QUALITY-010 should route retries to the real source path"
    )
    assert finding.metadata.get("hits") == ["src/app.py"], (
        "PY-QUALITY-010 should keep the matched path list"
    )
