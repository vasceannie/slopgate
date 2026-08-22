from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from .support import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    enroll_repo,
    evaluate_before,
    evaluate_stale_edit,
    raw_payload,
    write_source,
)

_UNRESOLVED_MUTATIONS = [
    pytest.param(
        "apply_patch",
        {"patchText": "not a patch"},
        "invalid",
        "invalid",
        id="invalid-patch",
    ),
    pytest.param(
        "edit",
        {"filePath": "missing.py"},
        "invalid",
        "invalid",
        id="invalid-edit",
    ),
    pytest.param(
        "write",
        {"filePath": "src/app.py", "content": "VALUE = 1\n"},
        "protocol_mismatch",
        "contract mismatch",
        id="protocol-mismatch",
    ),
    pytest.param(
        "custom_mutator",
        {"path": "src/app.py"},
        "unsupported",
        "Unknown OpenCode tool effect",
        id="unknown-mutator",
    ),
    pytest.param(
        "mcp__docs__write",
        {"path": "src/app.py"},
        "unsupported",
        "Unknown OpenCode tool effect",
        id="unknown-mcp-mutator",
    ),
]
_READ_ONLY_TOOLS = [
    pytest.param("read", id="read"),
    pytest.param("grep", id="grep"),
    pytest.param("glob", id="glob"),
    pytest.param("webfetch", id="webfetch"),
]


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected_status", "reason"),
    _UNRESOLVED_MUTATIONS,
)
def test_unresolved_mutating_projections_are_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
    expected_status: str,
    reason: str,
) -> None:
    contract_version = (
        "wrong-contract"
        if expected_status == "protocol_mismatch"
        else OPENCODE_TOOL_CONTRACT_VERSION
    )
    result, projection = evaluate_before(
        tmp_path, monkeypatch, tool_name, tool_input, contract_version=contract_version
    )

    assert projection["status"] == expected_status, (
        "unresolved mutating projections must keep their fail-closed status"
    )
    assert result.output is not None, "OpenCode must receive a rendered before-hook denial"
    assert result.output.get("action") == "block", (
        "unresolved mutating projections must not reach execution"
    )
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "the engine must inject the fail-closed projection finding"
    assert reason in str(result.output.get("reason")), (
        "the denial must name the unresolved projection cause"
    )


def test_stale_edit_projection_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, projection, outside = evaluate_stale_edit(tmp_path, monkeypatch)

    assert projection["status"] == "stale", (
        "symlink targets must not be treated as projected"
    )
    assert result.output is not None and result.output.get("action") == "block", (
        "stale mutation projections must be blocked"
    )
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "stale projections must trip the fail-closed finding"
    assert "stale" in str(result.output.get("reason"))
    assert outside.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "fail-closed projection must leave the external target unchanged"
    )


@pytest.mark.parametrize("tool_name", _READ_ONLY_TOOLS)
def test_known_read_only_tools_remain_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    result, _projection_meta = evaluate_before(
        tmp_path,
        monkeypatch,
        tool_name,
        {"path": "src/app.py", "pattern": "VALUE"},
    )

    assert result.output is None or result.output.get("action") != "block", (
        "known read-only OpenCode tools must remain available"
    )
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    ), "read-only tools must not trip unresolved-projection denial"


def test_projected_write_emits_one_finding_for_one_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    result = evaluate_payload(
        raw_payload(
            repo,
            "write",
            {"filePath": "src/app.py", "content": "def broken(:\n"},
        ),
        platform="opencode",
    )
    ast_findings = [
        finding for finding in result.findings if finding.rule_id == "PY-AST-001"
    ]

    assert len(ast_findings) == 1, "one projected write must produce one AST finding"


def test_projected_apply_patch_is_checked_as_complete_python_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    source = write_source(repo, "src/app.py", "VALUE = 1\n")
    patch_text = """*** Begin Patch
*** Update File: src/app.py
@@
-VALUE = 1
+def broken(:
*** End Patch"""

    result = evaluate_payload(
        raw_payload(repo, "apply_patch", {"patchText": patch_text}),
        platform="opencode",
    )

    assert any(finding.rule_id == "PY-AST-001" for finding in result.findings), (
        "projected full-file syntax failures must block in tool.execute.before"
    )
    assert result.output is not None, (
        "OpenCode should receive a rendered before-hook output"
    )
    assert result.output.get("action") == "block", (
        "OpenCode should receive a typed before-hook block action"
    )
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "preflight must leave the current file unchanged"
    )
