from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from .support import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    enroll_repo,
    evaluate_before,
    evaluate_stale_edit,
    raw_payload,
    write_source,
)

@dataclass(frozen=True)
class _ProjectionExpectation:
    tool_input: dict[str, object]
    expected_status: str
    reason: str


def _required_text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("projection expectation text must be a string")
    return value


_UNRESOLVED_MUTATIONS = [
    pytest.param(
        "apply_patch",
        {"patchText": "not a patch"},
        "invalid",
        "invalid",
        id="invalid-patch",
    ),
    pytest.param(
        "ApplyPatch",
        {"patchText": "not a patch"},
        "invalid",
        "invalid",
        id="invalid-pascal-case-patch",
    ),
    pytest.param(
        "edit",
        {"filePath": "missing.py"},
        "invalid",
        "invalid",
        id="invalid-edit",
    ),
]
_UNRESOLVED_MUTATION_CASES = [
    pytest.param(
        parameter.values[0],
        _ProjectionExpectation(
            tool_input=object_dict(parameter.values[1]),
            expected_status=_required_text(parameter.values[2]),
            reason=_required_text(parameter.values[3]),
        ),
        id=parameter.id,
    )
    for parameter in _UNRESOLVED_MUTATIONS
]
_READ_ONLY_TOOLS = [
    pytest.param("read", id="read"),
    pytest.param("grep", id="grep"),
    pytest.param("glob", id="glob"),
    pytest.param("background_output", id="background-output"),
    pytest.param("webfetch", id="webfetch"),
    pytest.param("gitnexus_context", id="unprojected-mcp-read"),
    pytest.param("LspDiagnostics", id="pascal-case-read"),
    pytest.param("CodegraphCodegraphExplore", id="multiword-pascal-case-read"),
    pytest.param("skill", id="host-control-tool"),
]
_UNPROJECTED_EFFECT_TOOLS = [
    pytest.param(
        "github_update_issue",
        {"path": "/repos/o/r/issues/1", "body": "fixed"},
        id="github-api-resource-path",
    ),
    pytest.param(
        "api_delete_resource",
        {"path": "/v1/items/1"},
        id="declared-api-resource-path",
    ),
    pytest.param(
        "interactive_bash",
        {"tmux_command": "send-keys -t dev 'touch src/app.py' Enter"},
        id="interactive-shell-wrapper",
    ),
    pytest.param(
        "skill_mcp",
        {
            "mcp_name": "fs",
            "tool_name": "write_file",
            "arguments": {"path": "src/app.py", "content": "VALUE = 1\n"},
        },
        id="mcp-dispatch-wrapper",
    ),
]
_UNCLASSIFIED_TOOLS = [
    pytest.param("custom_mutator", {"path": "src/app.py"}, id="unknown-mutator"),
    pytest.param(
        "mcp__docs__write",
        {"path": "src/app.py"},
        id="unknown-mcp-mutator",
    ),
    pytest.param(
        "custom_write",
        {"filename": "src/app.py", "content": "VALUE = 1\n"},
        id="unknown-filename-mutator",
    ),
]

_NON_STRICT_REPO_CONFIGS = [
    pytest.param(None, id="outside-repo"),
    pytest.param("[slopgate]\nenabled = false\n", id="relaxed-repo"),
]


@pytest.mark.parametrize(
    ("tool_name", "expectation"),
    _UNRESOLVED_MUTATION_CASES,
)
def test_unresolved_mutating_projections_are_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    expectation: _ProjectionExpectation,
) -> None:
    contract_version = (
        "wrong-contract"
        if expectation.expected_status == "protocol_mismatch"
        else OPENCODE_TOOL_CONTRACT_VERSION
    )
    result, projection = evaluate_before(
        tmp_path,
        monkeypatch,
        tool_name,
        expectation.tool_input,
        contract_version=contract_version,
    )

    assert projection["status"] == expectation.expected_status, (
        "unresolved mutating projections must keep their fail-closed status"
    )
    assert result.output is not None, "OpenCode must receive a rendered before-hook denial"
    assert result.output.get("action") == "block", (
        "unresolved mutating projections must not reach execution"
    )
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "the engine must inject the fail-closed projection finding"
    assert expectation.reason in str(result.output.get("reason")), (
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


@pytest.mark.parametrize("repo_config", _NON_STRICT_REPO_CONFIGS)
def test_unknown_tools_are_not_hard_denied_outside_strict_repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_config: str | None,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    if repo_config is not None:
        (repo / "slopgate.toml").write_text(repo_config, encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "slopgate-root"))

    result = evaluate_payload(
        raw_payload(repo, "custom_mutator", {"path": "src/app.py"}),
        platform="opencode",
    )

    assert result.output is None or result.output.get("action") != "block"
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    )


@pytest.mark.parametrize(("tool_name", "tool_input"), _UNPROJECTED_EFFECT_TOOLS)
def test_declared_unprojected_effects_remain_available_in_clean_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    result, projection = evaluate_before(
        tmp_path,
        monkeypatch,
        tool_name,
        tool_input,
    )

    assert projection["status"] == "unsupported", (
        "unprojected effects should remain outside local filesystem projection"
    )
    assert result.output is None or result.output.get("action") != "block", (
        "explicitly classified remote effects should remain available in clean state"
    )
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    ), "declared unprojected effects must not be reported as unknown mutations"


@pytest.mark.parametrize(("tool_name", "tool_input"), _UNCLASSIFIED_TOOLS)
def test_unclassified_tools_remain_available_in_clean_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    result, projection = evaluate_before(
        tmp_path,
        monkeypatch,
        tool_name,
        tool_input,
    )

    assert projection["status"] == "unsupported", (
        "unclassified tools should remain outside filesystem projection"
    )
    assert result.output is None or result.output.get("action") != "block", (
        "registry drift must not block unclassified tools while the repo is clean"
    )
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    ), "clean unclassified tools must not emit projection denials"


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
