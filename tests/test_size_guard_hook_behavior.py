"""Behavioral tests for hook-time oversized-module and god-class guards.

These tests intentionally describe desired hook behavior before implementing the
runtime parity fixes. They cover the variable payload shapes that can otherwise
pass through the hook layer before batch lint catches them later.
"""

from __future__ import annotations

import json
from pathlib import Path

from slopgate._types import ObjectDict, object_dict, string_value
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult, RuleFinding


GOD_CLASS_RULE = "PY-CODE-014"
OVERSIZED_MODULE_RULE = "PY-CODE-018"
QUALITY_LINT_RULE = "QUALITY-LINT-001"


def enroll_repo(repo: Path) -> None:
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "logs" / "async").mkdir(parents=True, exist_ok=True)
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )


def assignment_module(line_count: int) -> str:
    return "".join(f"VALUE_{idx} = None\n" for idx in range(line_count))


def class_with_body_lines(
    class_name: str = "HugeByLines", body_lines: int = 401
) -> str:
    # Use None assignments so the desired god-class/line-span tests are not
    # satisfied by unrelated magic-number rules first.
    body = "".join(f"    attr_{idx} = None\n" for idx in range(body_lines))
    return f"class {class_name}:\n" + body


def _add_file_patch(path: str, content: str) -> str:
    added = "".join(f"+{line}\n" for line in content.splitlines())
    return f"*** Begin Patch\n*** Add File: {path}\n{added}*** End Patch\n"


def pre_write_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def pre_patch_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Patch",
        "tool_input": {"patch": _add_file_patch(file_path, content)},
    }


def pre_edit_payload(
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


def opencode_before_edit_payload(
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


def pre_multiedit_payload(
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


def post_write_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
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


def post_bash_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
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


def opencode_before_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
    return {
        "session_id": "size-guard-test",
        "cwd": str(repo),
        "hook_event_name": "tool.execute.before",
        "tool_name": "write",
        "tool_input": {"filePath": file_path, "content": content},
    }


def opencode_after_payload(repo: Path, file_path: str, content: str) -> ObjectDict:
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


def result_text(result: EngineResult) -> str:
    output_text = json.dumps(result.output or {}, sort_keys=True)
    finding_text = "\n".join(_finding_text(finding) for finding in result.findings)
    return f"{output_text}\n{finding_text}".lower()


def finding_ids(result: EngineResult) -> list[str]:
    return [finding.rule_id for finding in result.findings]


def rule_count(result: EngineResult, rule_id: str) -> int:
    return sum(finding.rule_id == rule_id for finding in result.findings)


def findings_for_rule(result: EngineResult, rule_id: str) -> list[RuleFinding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def assert_hook_prevents(result: EngineResult, *, expected_text: str) -> None:
    decision = _output_decision(result)
    details = result_text(result)
    assert decision in {"deny", "block"}, (
        f"Expected hook to deny/block, got {decision!r}.\n{details}"
    )
    assert expected_text.lower() in details, (
        f"Expected hook evidence to mention {expected_text!r}.\n{details}"
    )


# Exported test support used by split test modules.
__all__ = (
    "EngineResult",
    "GOD_CLASS_RULE",
    "OVERSIZED_MODULE_RULE",
    "ObjectDict",
    "Path",
    "QUALITY_LINT_RULE",
    "RuleFinding",
    "_add_file_patch",
    "assignment_module",
    "class_with_body_lines",
    "enroll_repo",
    "finding_ids",
    "_finding_text",
    "findings_for_rule",
    "opencode_after_payload",
    "opencode_before_edit_payload",
    "opencode_before_payload",
    "_output_decision",
    "post_bash_payload",
    "post_write_payload",
    "pre_edit_payload",
    "pre_multiedit_payload",
    "pre_patch_payload",
    "pre_write_payload",
    "result_text",
    "rule_count",
    "assert_hook_prevents",
    "evaluate_payload",
    "json",
    "object_dict",
    "string_value",
)
