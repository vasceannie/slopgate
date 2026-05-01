"""Behavioral tests for hook-time oversized-module and god-class guards.

These tests intentionally describe desired hook behavior before implementing the
runtime parity fixes. They cover the variable payload shapes that can otherwise
pass through the hook layer before batch lint catches them later.
"""

from __future__ import annotations

import json
from pathlib import Path

from vibeforcer._types import ObjectDict, object_dict, string_value
from vibeforcer.engine import evaluate_payload
from vibeforcer.models import EngineResult, RuleFinding


def _enroll_repo(repo: Path) -> None:
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "logs" / "async").mkdir(parents=True, exist_ok=True)
    (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n", encoding="utf-8"
    )


def _assignment_module(line_count: int) -> str:
    return "".join(f"VALUE_{idx} = None\n" for idx in range(line_count))


def _class_with_body_lines(class_name: str = "HugeByLines", body_lines: int = 401) -> str:
    # Use None assignments so the desired god-class/line-span tests are not
    # satisfied by unrelated magic-number rules first.
    body = "".join(f"    attr_{idx} = None\n" for idx in range(body_lines))
    return f"class {class_name}:\n" + body


def _add_file_patch(path: str, content: str) -> str:
    added = "".join(f"+{line}\n" for line in content.splitlines())
    return f"*** Begin Patch\n*** Add File: {path}\n{added}*** End Patch\n"


def _pre_write_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def _pre_patch_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Patch",
        "tool_input": {"patch": _add_file_patch(file_path, content)},
    }


def _pre_edit_payload(
    repo: Path,
    file_path: str,
    existing_content: str,
    old_string: str,
    new_string: str,
) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(existing_content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": file_path,
            "old_string": old_string,
            "new_string": new_string,
        },
    }


def _opencode_before_edit_payload(
    repo: Path,
    file_path: str,
    existing_content: str,
    old_string: str,
    new_string: str,
) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(existing_content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "tool.execute.before",
        "tool_name": "edit",
        "tool_input": {
            "filePath": file_path,
            "oldString": old_string,
            "newString": new_string,
        },
    }


def _pre_multiedit_payload(
    repo: Path,
    file_path: str,
    existing_content: str,
    old_string: str,
    new_string: str,
) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(existing_content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": file_path,
            "edits": [
                {
                    "old_string": old_string,
                    "new_string": new_string,
                }
            ],
        },
    }


def _post_write_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "tool_response": {"filePath": file_path, "success": True},
    }


def _post_bash_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": f"python tools/generate.py > {file_path}"},
        "tool_response": {"exit_code": 0},
    }


def _opencode_before_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "tool.execute.before",
        "tool_name": "write",
        "tool_input": {"filePath": file_path, "content": content},
    }


def _opencode_after_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "tool.execute.after",
        "tool_name": "write",
        "tool_input": {"filePath": file_path},
        "tool_response": {"filePath": file_path, "success": True},
    }


def _output_decision(result: EngineResult) -> str | None:
    output = result.output
    if output is None:
        return None
    direct_decision = string_value(output.get("decision"))
    if direct_decision == "block":
        return "block"
    action = string_value(output.get("action"))
    if action == "block":
        return "block"
    hook_specific = object_dict(output.get("hookSpecificOutput"))
    permission_decision = string_value(hook_specific.get("permissionDecision"))
    if permission_decision == "deny":
        return "deny"
    nested_decision = object_dict(hook_specific.get("decision"))
    behavior = string_value(nested_decision.get("behavior"))
    if behavior in {"deny", "block"}:
        return behavior
    return None


def _finding_text(finding: RuleFinding) -> str:
    metadata = json.dumps(finding.metadata, sort_keys=True)
    return " ".join(
        part
        for part in [finding.rule_id, finding.title, finding.message, metadata]
        if part
    )


def _result_text(result: EngineResult) -> str:
    output_text = json.dumps(result.output or {}, sort_keys=True)
    finding_text = "\n".join(_finding_text(finding) for finding in result.findings)
    return f"{output_text}\n{finding_text}".lower()


def _finding_ids(result: EngineResult) -> list[str]:
    return [finding.rule_id for finding in result.findings]


def _findings_for_rule(result: EngineResult, rule_id: str) -> list[RuleFinding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _assert_hook_prevents(result: EngineResult, *, expected_text: str) -> None:
    decision = _output_decision(result)
    details = _result_text(result)
    assert decision in {"deny", "block"}, (
        f"Expected hook to deny/block, got {decision!r}.\n{details}"
    )
    assert expected_text.lower() in details, (
        f"Expected hook evidence to mention {expected_text!r}.\n{details}"
    )


class TestOversizedModuleHookBehavior:
    def test_pretool_write_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/soft_oversized.py", _assignment_module(351))
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_pretool_write_blocks_hard_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/hard_oversized.py", _assignment_module(601))
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_pretool_write_gives_conftest_split_guidance(self, tmp_path: Path) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "tests/tui/conftest.py", _assignment_module(601))
        )

        _assert_hook_prevents(result, expected_text="conftest")
        findings = _findings_for_rule(result, "PY-CODE-018")
        assert len(findings) == 1
        assert findings[0].metadata["split_scenario"] == "conftest"
        assert "fixture registry" in (findings[0].additional_context or "")
        assert "tests/<area>/support/" in (findings[0].additional_context or "")

    def test_pretool_write_gives_module_to_package_guidance(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/dashboard.py", _assignment_module(601))
        )

        _assert_hook_prevents(result, expected_text="module-to-package")
        findings = _findings_for_rule(result, "PY-CODE-018")
        assert len(findings) == 1
        assert findings[0].metadata["split_scenario"] == "module-to-package"
        assert "re-exporting the old public API" in (findings[0].additional_context or "")
        assert "resources, or builders" in (findings[0].additional_context or "")

    def test_pretool_write_gives_entrypoint_router_guidance(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/routes.py", _assignment_module(601))
        )

        _assert_hook_prevents(result, expected_text="entrypoint-or-router")
        findings = _findings_for_rule(result, "PY-CODE-018")
        assert len(findings) == 1
        assert findings[0].metadata["split_scenario"] == "entrypoint-or-router"
        assert "commands/routes stay thin" in (findings[0].additional_context or "")

    def test_pretool_write_gives_package_init_guidance(self, tmp_path: Path) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/__init__.py", _assignment_module(601))
        )

        _assert_hook_prevents(result, expected_text="package-init")
        findings = _findings_for_rule(result, "PY-CODE-018")
        assert len(findings) == 1
        assert findings[0].metadata["split_scenario"] == "package-init"
        assert "facade only" in (findings[0].additional_context or "")

    def test_opencode_before_write_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_before_payload(
                tmp_path, "src/opencode_soft.py", _assignment_module(351)
            ),
            platform="opencode",
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_pretool_patch_add_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_patch_payload(tmp_path, "src/patched_soft.py", _assignment_module(351))
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_pretool_edit_blocks_file_already_over_soft_module_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/already_oversized.py",
                _assignment_module(351),
                "VALUE_0 = None\n",
                "VALUE_0 = None  # touched\n",
            )
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_pretool_edit_blocks_edit_that_pushes_module_over_soft_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/pushed_oversized.py",
                _assignment_module(350),
                "VALUE_349 = None\n",
                "VALUE_349 = None\nVALUE_350 = None\n",
            )
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_opencode_before_edit_blocks_edit_that_pushes_module_over_soft_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_before_edit_payload(
                tmp_path,
                "src/opencode_pushed_oversized.py",
                _assignment_module(350),
                "VALUE_349 = None\n",
                "VALUE_349 = None\nVALUE_350 = None\n",
            ),
            platform="opencode",
        )
        _assert_hook_prevents(result, expected_text="oversized")

    def test_posttool_write_blocks_soft_oversized_python_module_from_tool_response_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_write_payload(
                tmp_path, "src/post_soft.py", _assignment_module(351)
            )
        )
        _assert_hook_prevents(result, expected_text="oversized-module-soft")
        assert _finding_ids(result).count("QUALITY-LINT-001") == 1
        assert "PY-CODE-018" not in _finding_ids(result)
        assert "module-to-package split plan" in _result_text(result)

    def test_posttool_write_uses_single_conftest_oversized_recommendation(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_write_payload(
                tmp_path, "tests/tui/conftest.py", _assignment_module(351)
            )
        )

        _assert_hook_prevents(result, expected_text="oversized-module-soft")
        assert _finding_ids(result).count("QUALITY-LINT-001") == 1
        assert "PY-CODE-018" not in _finding_ids(result)
        details = _result_text(result)
        assert "conftest split" in details
        assert "fixture registry" in details

    def test_opencode_after_write_blocks_soft_oversized_python_module_from_file_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_after_payload(
                tmp_path, "src/opencode_post_soft.py", _assignment_module(351)
            ),
            platform="opencode",
        )
        _assert_hook_prevents(result, expected_text="oversized-module-soft")
        assert _finding_ids(result).count("QUALITY-LINT-001") == 1
        assert "PY-CODE-018" not in _finding_ids(result)


class TestGodClassLineSpanHookBehavior:
    def test_pretool_write_blocks_god_class_by_line_span(self, tmp_path: Path) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(
                tmp_path, "src/god_by_lines.py", _class_with_body_lines()
            )
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_opencode_before_write_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_before_payload(
                tmp_path, "src/opencode_god.py", _class_with_body_lines()
            ),
            platform="opencode",
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_pretool_patch_add_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_patch_payload(tmp_path, "src/patched_god.py", _class_with_body_lines())
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_pretool_edit_blocks_file_already_over_god_class_line_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/already_god.py",
                _class_with_body_lines(body_lines=401),
                "    attr_0 = None\n",
                "    attr_0 = None  # touched\n",
            )
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_pretool_edit_blocks_edit_that_pushes_class_over_line_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/pushed_god.py",
                _class_with_body_lines(body_lines=400),
                "    attr_399 = None\n",
                "    attr_399 = None\n    attr_400 = None\n",
            )
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_pretool_multiedit_blocks_edit_that_pushes_class_over_line_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_multiedit_payload(
                tmp_path,
                "src/multiedit_pushed_god.py",
                _class_with_body_lines(body_lines=400),
                "    attr_399 = None\n",
                "    attr_399 = None\n    attr_400 = None\n",
            )
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_posttool_write_blocks_god_class_by_line_span_from_tool_response_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_write_payload(tmp_path, "src/post_god.py", _class_with_body_lines())
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_opencode_after_write_blocks_god_class_by_line_span_from_file_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_after_payload(
                tmp_path, "src/opencode_post_god.py", _class_with_body_lines()
            ),
            platform="opencode",
        )
        _assert_hook_prevents(result, expected_text="god-class")

    def test_posttool_bash_redirection_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_bash_payload(tmp_path, "src/generated_god.py", _class_with_body_lines())
        )
        _assert_hook_prevents(result, expected_text="god-class")
