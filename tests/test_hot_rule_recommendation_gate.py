"""Behavioral gates for hot-rule prompt and hook-reason language."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from vibeforcer import engine
from vibeforcer.context import build_context
from vibeforcer.engine import evaluate_payload, render_output
from vibeforcer.models import EngineResult, RuleFinding, Severity

from tests import support as test_support


def _enroll_repo(repo: Path) -> None:
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n", encoding="utf-8"
    )


def _write_payload(repo: Path, file_path: str, content: str) -> dict[str, object]:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "session_id": "hot-rule-language",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def _post_write_payload(repo: Path, file_path: str, content: str) -> dict[str, object]:
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "session_id": "hot-rule-language",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "tool_response": {"filePath": file_path, "success": True},
    }


def _additional_context(result: EngineResult) -> str:
    output = test_support.hook_output(result)
    return test_support.required_string(output, "additionalContext")


def _pathless_quality_output(repo: Path) -> dict[str, object]:
    ctx = build_context(
        {
            "session_id": "hot-rule-pathless",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {},
            "tool_response": {"success": True},
        }
    )
    findings = [
        RuleFinding(
            rule_id="QUALITY-LINT-001",
            title="Touched-file lint failed",
            severity=Severity.HIGH,
            decision="block",
            message="Touched-file lint detectors found issues. Repair touched files.",
        )
    ]
    apply_loop_aware_steering = cast(
        Callable[[object, list[RuleFinding]], None],
        getattr(engine, "_apply_loop_aware_steering"),
    )
    apply_loop_aware_steering(ctx, findings)
    output = render_output(ctx, findings)
    assert output is not None
    return output


def _assert_context_only_advisory(result: EngineResult, rule_id: str) -> None:
    finding = next(item for item in result.findings if item.rule_id == rule_id)
    assert finding.decision == "context"
    assert result.output is None
    message = finding.message or ""
    assert "Advisory only" in message
    assert "do not retry the write solely for this" in message


def test_quality_lint_posttool_reason_marks_already_mutated_repair(
    tmp_path: Path,
) -> None:
    _enroll_repo(tmp_path)
    content = "".join(f"VALUE_{idx} = None\n" for idx in range(351))

    result = evaluate_payload(_post_write_payload(tmp_path, "src/post_soft.py", content))

    test_support.assert_blocked(result, "QUALITY-LINT-001")
    context = _additional_context(result)
    assert "already-mutated" in context
    assert "Do not continue feature work" in context
    assert "reread the touched file" in context
    assert "smallest repo-root quality command" in context
    assert "fix only the reported collector" in context
    output_text = str(result.output)
    assert "First lint violation detail" in output_text
    assert "scaffold:" in output_text


def test_quality_lint_pathless_reason_names_last_edit_fallback(tmp_path: Path) -> None:
    _enroll_repo(tmp_path)
    output = _pathless_quality_output(tmp_path)
    reason = test_support.output_string(output, "reason")
    context = test_support.required_string(
        test_support.nested_output(output, "hookSpecificOutput"), "additionalContext"
    )
    assert "QUALITY-LINT-001" in reason
    assert "Path was not extracted" in context
    assert "file you just wrote/edited" in context
    assert "do not blindly rerun" in context


def test_thin_wrapper_reason_lists_real_boundary_allowlist(tmp_path: Path) -> None:
    _enroll_repo(tmp_path)
    content = """def target(value):
    return value


def wrap(value):
    return target(value)
"""

    result = evaluate_payload(_write_payload(tmp_path, "src/wrap.py", content))

    test_support.assert_denied_by(result, "PY-CODE-013")
    context = _additional_context(result)
    assert "validates/normalizes" in context
    assert "centralizes policy" in context
    assert "adapts one interface" in context
    assert "hides unstable third-party API" in context


def test_long_params_reason_is_role_aware_for_test_helpers(tmp_path: Path) -> None:
    _enroll_repo(tmp_path)
    content = """def make_case(name, value, expected, mode, flag, retries, timeout):
    return (name, value, expected, mode, flag, retries, timeout)
"""

    result = evaluate_payload(_write_payload(tmp_path, "tests/test_cases.py", content))

    test_support.assert_denied_by(result, "PY-CODE-009")
    context = _additional_context(result)
    assert "helper is pretending to be a constructor" in context
    assert "Case dataclass" in context
    assert "builder defaults" in context


def test_long_params_reason_is_role_aware_for_production_code(tmp_path: Path) -> None:
    _enroll_repo(tmp_path)
    content = """def build(name, value, expected, mode, flag, retries, timeout):
    return (name, value, expected, mode, flag, retries, timeout)
"""

    result = evaluate_payload(_write_payload(tmp_path, "src/params.py", content))

    test_support.assert_denied_by(result, "PY-CODE-009")
    context = _additional_context(result)
    assert "group by semantic meaning" in context
    assert "not arbitrary parameter bags" in context


def test_repo_prompt_context_preflights_hot_rules(bundle_root: Path) -> None:
    prompt_context = (
        bundle_root / "src" / "vibeforcer" / "resources" / "prompt_context" / "repo.md"
    ).read_text(encoding="utf-8")

    assert "Hot Hook Preflight" in prompt_context
    assert "PY-CODE-013" in prompt_context
    assert "validates/normalizes" in prompt_context
    assert "PY-CODE-009" in prompt_context
    assert "Case` dataclass" in prompt_context
    assert "QUALITY-LINT-001" in prompt_context
    assert "smallest repo-root quality command" in prompt_context
    assert "PY-CODE-012" in prompt_context
    assert "PY-IMPORT-001" in prompt_context
    assert "Do not retry solely" in prompt_context


def test_context_only_hot_rules_say_advisory_not_retry_now(tmp_path: Path) -> None:
    _enroll_repo(tmp_path)
    import_fanout = "from math import sin, cos, tan, asin, acos, atan, sqrt, floor, ceil\n"
    feature_envy = """service = object()


def render():
    return (
        service.alpha
        + service.beta
        + service.gamma
        + service.delta
        + service.epsilon
        + service.zeta
    )
"""

    import_result = evaluate_payload(_write_payload(tmp_path, "src/imports.py", import_fanout))
    envy_result = evaluate_payload(_write_payload(tmp_path, "src/envy.py", feature_envy))

    _assert_context_only_advisory(import_result, "PY-IMPORT-001")
    _assert_context_only_advisory(envy_result, "PY-CODE-012")
