"""Leaked Python parser exceptions must normalize into structured PY-AST-001 findings.

Covers the slopgate-gfk.4 regression: an IndentationError escaping token generation
inside PY-CODE-010 used to surface as a ``PY-CODE-010: <exception>`` runtime error
instead of one structured PY-AST-001 parse-failure finding.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.constants import METADATA_PATH
from slopgate.context import HookContext
from slopgate.engine import evaluate_payload
from slopgate.engine._runner import EvalAccumulator, _run_rule
from slopgate.models import EngineResult, RuleFinding
from slopgate.rules.base import Rule
from tests.test_ast_rules import BUNDLE_ROOT
from tests.adapters.test_opencode_projection.support import (
    enroll_repo,
    evaluate_stale_edit,
    raw_payload,
)
from tests.test_enrichment_public_api import context_for_source

BROKEN_INDENT_SOURCE = (
    "def compute(value: int) -> int:\n"
    "    total = value + 1\n"
    "   return total\n"
)


def _py_ast_findings(result: EngineResult) -> list[RuleFinding]:
    return [finding for finding in result.findings if finding.rule_id == "PY-AST-001"]


def _single_py_ast_finding(result: EngineResult, expected_path: str) -> RuleFinding:
    findings = _py_ast_findings(result)
    assert len(findings) == 1, f"expected one PY-AST-001 finding: {result.findings!r}"
    assert findings[0].metadata[METADATA_PATH] == expected_path, (
        f"finding must point at the evaluated path: {findings[0].metadata!r}"
    )
    return findings[0]


def _assert_no_parser_leak(result: EngineResult) -> None:
    assert all(
        finding.rule_id != "PY-CODE-010" for finding in result.findings
    ), "incomplete tokenization must not produce long-line findings"
    assert all(
        "PY-CODE-010" not in error for error in result.errors
    ), f"parser exceptions must not leak as PY-CODE-010 runtime errors: {result.errors!r}"


def _assert_projected_parse_diagnostic(finding: RuleFinding) -> None:
    assert finding.metadata["provenance"] == "projected_content", (
        f"projected mutation must identify projected content: {finding.metadata!r}"
    )
    message = finding.message
    assert message is not None, "parse findings must provide a diagnostic message"
    assert "IndentationError" in message, (
        f"finding message must render parser type: {message!r}"
    )
    assert "unindent does not match" in message, (
        f"finding message must render parser message: {message!r}"
    )
    assert "line 3" in message, (
        f"finding message must render parser line: {message!r}"
    )
    assert "offset" in message, (
        f"finding message must render parser offset: {message!r}"
    )
    recovery = finding.additional_context
    assert recovery is not None, "parse findings must provide recovery guidance"
    assert recovery not in message, "recovery guidance must not be duplicated"


def test_write_indentation_failure_emits_structured_py_ast_finding() -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "src/broken_indent.py",
            "content": BROKEN_INDENT_SOURCE,
        },
        "cwd": str(BUNDLE_ROOT),
    }

    result = evaluate_payload(payload)

    finding = _single_py_ast_finding(result, "src/broken_indent.py")
    meta = finding.metadata
    assert meta["kind"] == "parse_error", f"expected parse_error kind: {meta!r}"
    assert meta["exception_type"] == "IndentationError", (
        f"expected IndentationError provenance in metadata: {meta!r}"
    )
    assert isinstance(meta["parser_message"], str), (
        f"parser message must be preserved as a string: {meta!r}"
    )
    assert "unindent does not match" in meta["parser_message"], (
        f"original parser message must be preserved: {meta!r}"
    )
    assert meta["line"] == 3, f"expected offending line 3 in metadata: {meta!r}"
    offset = meta["offset"]
    assert isinstance(offset, int), f"offset must be an int: {meta!r}"
    assert offset >= 1, f"expected positive offset in metadata: {meta!r}"
    serialized = json.dumps(meta)
    assert "total = value" not in serialized, (
        f"raw source must not be stored in metadata: {serialized!r}"
    )
    _assert_no_parser_leak(result)


def test_projected_opencode_mutation_normalizes_indentation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)

    result = evaluate_payload(
        raw_payload(
            repo,
            "write",
            {"filePath": "src/app.py", "content": BROKEN_INDENT_SOURCE},
        ),
        platform="opencode",
    )

    finding = _single_py_ast_finding(result, "src/app.py")
    assert finding.metadata["exception_type"] == "IndentationError", (
        f"projected mutation must preserve parser provenance: {finding.metadata!r}"
    )
    _assert_projected_parse_diagnostic(finding)
    _assert_no_parser_leak(result)


def test_stale_native_edit_does_not_become_projected_parse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, projection, _outside = evaluate_stale_edit(tmp_path, monkeypatch)

    assert projection["status"] == "stale", (
        f"fixture must exercise native stale-edit parity: {projection!r}"
    )
    assert not _py_ast_findings(result), (
        "native hashline parity failures must not be reported as projected AST failures"
    )


def test_posttooluse_disk_file_indentation_failure_normalizes(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "broken_indent.py").write_text(
        BROKEN_INDENT_SOURCE,
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "broken_indent.py"},
        "cwd": str(tmp_path),
        "session_id": "t",
    }

    result = evaluate_payload(payload)

    finding = _single_py_ast_finding(result, "broken_indent.py")
    assert finding.metadata["exception_type"] == "IndentationError", (
        f"disk-file evaluation must preserve parser provenance: {finding.metadata!r}"
    )
    _assert_no_parser_leak(result)


def test_valid_long_line_still_produces_py_code_010() -> None:
    long_line = "value = " + " + ".join(f"part_{index}" for index in range(30))
    source = f"def long_expression() -> None:\n    {long_line}\n"
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/long_line.py", "content": source},
        "cwd": str(BUNDLE_ROOT),
    }

    result = evaluate_payload(payload)

    long_line_findings = [
        finding for finding in result.findings if finding.rule_id == "PY-CODE-010"
    ]
    assert len(long_line_findings) == 1, (
        f"valid long-line input must still be reported: {result.findings!r}"
    )
    assert long_line_findings[0].metadata["line"] == 2, (
        f"long-line finding must point at the offending line: "
        f"{long_line_findings[0].metadata!r}"
    )
    assert not _py_ast_findings(result), "valid module must not emit parse failures"
    assert result.errors == [], f"clean parse must not record errors: {result.errors!r}"


def test_unexpected_rule_exception_still_populates_runtime_errors() -> None:
    class ExplodingRule(Rule):
        rule_id = "TEST-EXPLODE-001"
        title = "Explodes on evaluate"
        events = ()

        def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
            raise ValueError("boom")

    ctx = context_for_source(Path(BUNDLE_ROOT), "VALUE = 1\n", path="sample.py")
    acc = EvalAccumulator()

    _run_rule(ExplodingRule(), ctx, "claude", acc)

    assert acc.errors == ["TEST-EXPLODE-001: boom"], (
        f"non-parser rule exceptions must stay visible as runtime errors: {acc.errors!r}"
    )
