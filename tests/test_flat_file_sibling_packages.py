"""Regression tests for package-split sibling module naming.

The hook should stop agents from creating flat prefix_*.py clusters when the
shape should be a subpackage with __init__.py re-exports.
"""

from __future__ import annotations

from pathlib import Path

from vibeforcer._types import ObjectDict
from vibeforcer.engine import evaluate_payload
from tests.support import WriteBuilder, assert_denied_by, assert_not_denied, finding_ids


def _posttool_write(tmp_project: Path, rel_path: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": rel_path, "content": "pass\n"},
        "tool_response": {"filePath": rel_path, "success": True},
    }


def _bash_payload(tmp_project: Path, command: str, event: str = "PreToolUse") -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _patch_payload(tmp_project: Path, patch: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PreToolUse",
        "tool_name": "Patch",
        "tool_input": {"patch": patch},
    }


def _bash_package_move_command() -> str:
    return " && ".join(
        [
            "mkdir -p src/agents/result",
            "mv src/agents/result_models.py src/agents/result/models.py",
            "mv src/agents/result_runner.py src/agents/result/runner.py",
            "mv src/agents/result_reconciliation.py src/agents/result/reconciliation.py",
        ]
    )


def _write_completed_package_move(tmp_project: Path) -> None:
    pkg = tmp_project / "src" / "agents"
    target = pkg / "result"
    target.mkdir(parents=True, exist_ok=True)
    for old_name, new_name in (
        ("result_models.py", "models.py"),
        ("result_runner.py", "runner.py"),
        ("result_reconciliation.py", "reconciliation.py"),
    ):
        old_path = pkg / old_name
        _ = old_path.write_text("pass\n", encoding="utf-8")
        old_path.rename(target / new_name)
    _ = (target / "__init__.py").write_text("", encoding="utf-8")


def test_pretool_blocks_third_plain_prefix_sibling(
    tmp_project: Path, pretool_write: WriteBuilder
) -> None:
    pkg = tmp_project / "src" / "agents"
    pkg.mkdir(parents=True, exist_ok=True)
    _ = (pkg / "result_models.py").write_text("pass\n", encoding="utf-8")
    _ = (pkg / "result_runner.py").write_text("pass\n", encoding="utf-8")

    result = evaluate_payload(
        pretool_write("src/agents/result_reconciliation.py", "pass\n", str(tmp_project))
    )

    assert_denied_by(result, "PY-CODE-017", "sub-package")
    findings = [finding for finding in result.findings if finding.rule_id == "PY-CODE-017"]
    assert len(findings) == 1, f"expected one PY-CODE-017 finding, got {findings!r}"
    assert "code-hygiene-refactor" in (findings[0].additional_context or ""), (
        "finding should route agents to the hygiene recovery skill"
    )
    assert "python/project-structure" in (findings[0].additional_context or ""), (
        "finding should cite the project-structure rule shard"
    )
    assert str(findings[0].metadata.get("path", "")).endswith("result_models.py"), (
        f"finding path should point at an existing sibling, got {findings[0].metadata!r}"
    )


def test_posttool_blocks_existing_plain_prefix_cluster(tmp_project: Path) -> None:
    pkg = tmp_project / "src" / "agents"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in ("result_models.py", "result_runner.py", "result_reconciliation.py"):
        _ = (pkg / name).write_text("pass\n", encoding="utf-8")

    result = evaluate_payload(
        _posttool_write(tmp_project, "src/agents/result_reconciliation.py")
    )

    ids = finding_ids(result)
    assert "PY-CODE-017" in ids


def test_pretool_allows_mechanical_bash_move_into_package(tmp_project: Path) -> None:
    pkg = tmp_project / "src" / "agents"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in ("result_models.py", "result_runner.py", "result_reconciliation.py"):
        _ = (pkg / name).write_text("pass\n", encoding="utf-8")

    command = " && ".join(
        [
            "mkdir -p src/agents/result",
            "mv src/agents/result_models.py src/agents/result/models.py",
            "mv src/agents/result_runner.py src/agents/result/runner.py",
            "mv src/agents/result_reconciliation.py src/agents/result/reconciliation.py",
        ]
    )
    result = evaluate_payload(_bash_payload(tmp_project, command))

    assert "PY-CODE-017" not in finding_ids(result)


def test_posttool_allows_completed_bash_move_into_package(tmp_project: Path) -> None:
    _write_completed_package_move(tmp_project)

    result = evaluate_payload(
        _bash_payload(tmp_project, _bash_package_move_command(), event="PostToolUse")
    )

    assert "PY-CODE-017" not in finding_ids(result)


def test_pretool_allows_single_patch_that_converts_cluster_to_package(
    tmp_project: Path,
) -> None:
    pkg = tmp_project / "src" / "agent"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in (
        "runner_backend.py",
        "runner_helpers.py",
        "runner_judge.py",
        "runner_postprocess.py",
    ):
        _ = (pkg / name).write_text("pass\n", encoding="utf-8")

    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Delete File: src/agent/runner_backend.py",
            "*** Delete File: src/agent/runner_helpers.py",
            "*** Delete File: src/agent/runner_judge.py",
            "*** Delete File: src/agent/runner_postprocess.py",
            "*** Add File: src/agent/runner/__init__.py",
            "+from .backend import run_backend",
            "*** Add File: src/agent/runner/backend.py",
            "+def run_backend() -> None:",
            "+    return None",
            "*** Add File: src/agent/runner/helpers.py",
            "+HELPERS = ()",
            "*** Add File: src/agent/runner/judge.py",
            "+JUDGES = ()",
            "*** Add File: src/agent/runner/postprocess.py",
            "+POSTPROCESSORS = ()",
            "*** End Patch",
        ]
    )
    result = evaluate_payload(_patch_payload(tmp_project, patch))

    assert "PY-CODE-017" not in finding_ids(result)


def test_pretool_still_blocks_patch_that_leaves_flat_cluster(tmp_project: Path) -> None:
    pkg = tmp_project / "src" / "agent"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in (
        "runner_backend.py",
        "runner_helpers.py",
        "runner_judge.py",
        "runner_postprocess.py",
    ):
        _ = (pkg / name).write_text("pass\n", encoding="utf-8")

    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Delete File: src/agent/runner_backend.py",
            "*** Add File: src/agent/runner/backend.py",
            "+def run_backend() -> None:",
            "+    return None",
            "*** End Patch",
        ]
    )
    result = evaluate_payload(_patch_payload(tmp_project, patch))

    assert "PY-CODE-017" in finding_ids(result)


def test_posttool_bash_still_blocks_cluster_left_after_command(tmp_project: Path) -> None:
    pkg = tmp_project / "src" / "agents"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in ("result_models.py", "result_runner.py", "result_reconciliation.py"):
        _ = (pkg / name).write_text("pass\n", encoding="utf-8")

    result = evaluate_payload(
        _bash_payload(
            tmp_project,
            "touch src/agents/result_reconciliation.py",
            event="PostToolUse",
        )
    )

    assert "PY-CODE-017" in finding_ids(result)


def test_pretool_blocks_prefix_file_next_to_same_named_package(
    tmp_project: Path, pretool_write: WriteBuilder
) -> None:
    pkg = tmp_project / "src" / "agents"
    (pkg / "context").mkdir(parents=True, exist_ok=True)
    _ = (pkg / "context" / "__init__.py").write_text("", encoding="utf-8")

    result = evaluate_payload(
        pretool_write("src/agents/context_models.py", "pass\n", str(tmp_project))
    )
    assert_denied_by(result, "PY-CODE-017", "context/")
    assert "PY-CODE-017" in finding_ids(result), (
        "prefix module next to same-named package should trigger flat-package guard"
    )


def test_pretool_allows_common_single_underscore_module_without_cluster(
    tmp_project: Path, pretool_write: WriteBuilder
) -> None:
    pkg = tmp_project / "src" / "evaluation"
    pkg.mkdir(parents=True, exist_ok=True)

    result = evaluate_payload(
        pretool_write("src/evaluation/judge_per_field.py", "pass\n", str(tmp_project))
    )

    assert_not_denied(result)
    assert "PY-CODE-017" not in finding_ids(result), (
        "single common underscore module should not be mistaken for a flat cluster"
    )


def test_pretool_allows_test_file_convention(
    tmp_project: Path, pretool_write: WriteBuilder
) -> None:
    tests_dir = tmp_project / "tests" / "planning"
    tests_dir.mkdir(parents=True, exist_ok=True)
    _ = (tests_dir / "test_alpha.py").write_text("pass\n", encoding="utf-8")
    _ = (tests_dir / "test_beta.py").write_text("pass\n", encoding="utf-8")

    result = evaluate_payload(
        pretool_write("tests/planning/test_gamma.py", "pass\n", str(tmp_project))
    )

    assert_not_denied(result)
    assert "PY-CODE-017" not in finding_ids(result), (
        "test_<name>.py naming convention should not be blocked as a package split"
    )
