"""Behavioral gates for hot-rule prompt and hook-reason language."""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import cast
from slopgate.context import build_context
from slopgate.engine import evaluate_payload, render_output
from slopgate.engine._hints import quality_lint_hint
from slopgate.engine import _retry
from slopgate.models import EngineResult, RuleFinding, Severity
from tests import support


def enroll_repo(repo: Path) -> None:
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )


def write_payload(repo: Path, file_path: str, content: str) -> dict[str, object]:
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


def post_write_payload(repo: Path, file_path: str, content: str) -> dict[str, object]:
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


def additional_context(result: EngineResult) -> str:
    output = support.hook_output(result)
    return support.required_string(output, "additionalContext")


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
        getattr(_retry, "apply_loop_aware_steering"),
    )
    apply_loop_aware_steering(ctx, findings)
    output = render_output(ctx, findings)
    assert output is not None
    return output


def _assert_context_only_advisory(result: EngineResult, rule_id: str) -> None:
    finding = next((item for item in result.findings if item.rule_id == rule_id))
    assert finding.decision == "context"
    assert result.output is None
    message = finding.message or ""
    assert "Advisory only" in message
    assert "do not retry the write solely for this" in message


def _assert_quality_lint_repair_context(context: str, output_text: str) -> None:
    required_context = [
        "already-mutated",
        "Do not continue feature work",
        "reread the touched file",
        "smallest repo-root quality command",
        "from the repo root, run `slopgate lint check`",
        "fix only the reported collector",
    ]
    missing_context = [phrase for phrase in required_context if phrase not in context]
    assert missing_context == [], "QUALITY-LINT-001 repair context lost guidance"
    assert "Blocking lint collector details" in output_text, (
        "QUALITY-LINT-001 output should name blocking lint collector details"
    )
    assert "scaffold:" in output_text, (
        "QUALITY-LINT-001 output should include prescriptive scaffold text"
    )


def _assert_pathless_quality_fallback(reason: str, context: str) -> None:
    assert "QUALITY-LINT-001" in reason, "pathless fallback should name lint rule"
    required_context = [
        "Path was not extracted",
        "file you just wrote/edited",
        "do not blindly rerun",
    ]
    missing_context = [phrase for phrase in required_context if phrase not in context]
    assert missing_context == [], "pathless lint fallback should steer recovery"


def _assert_boundary_allowlist_context(context: str) -> None:
    expected_boundary_roles = [
        "validates/normalizes",
        "centralizes policy",
        "adapts one interface",
        "hides unstable third-party API",
    ]
    missing_roles = [role for role in expected_boundary_roles if role not in context]
    assert missing_roles == [], "thin-wrapper context lost boundary allowlist roles"


def _assert_hot_prompt_preflight(prompt_context: str) -> None:
    expected_preflight_anchors = [
        "Hot Hook Preflight",
        "PY-CODE-013",
        "validates/normalizes",
        "PY-CODE-009",
        "Case` dataclass",
        "QUALITY-LINT-001",
        "smallest repo-root quality command",
        "PY-CODE-012",
        "PY-IMPORT-001",
        "Do not retry solely",
    ]
    missing_anchors = [
        anchor for anchor in expected_preflight_anchors if anchor not in prompt_context
    ]
    assert missing_anchors == [], "repo prompt context lost hot-rule preflight anchors"


def test_quality_lint_posttool_reason_marks_already_mutated_repair(
    tmp_path: Path,
) -> None:
    enroll_repo(tmp_path)
    content = "".join((f"VALUE_{idx} = None\n" for idx in range(351)))
    result = evaluate_payload(post_write_payload(tmp_path, "src/post_soft.py", content))
    support.assert_blocked(result, "QUALITY-LINT-001")
    context = additional_context(result)
    assert "Blocking lint collector details" in str(result.output)
    _assert_quality_lint_repair_context(context, str(result.output))


def test_quality_lint_pathless_reason_names_last_edit_fallback(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    output = _pathless_quality_output(tmp_path)
    reason = support.output_string(output, "reason")
    context = support.required_string(
        support.nested_output(output, "hookSpecificOutput"), "additionalContext"
    )
    assert "QUALITY-LINT-001" in reason
    _assert_pathless_quality_fallback(reason, context)


def test_quality_lint_hint_public_helper_routes_collectors(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    ctx = build_context(post_write_payload(tmp_path, "src/post_soft.py", "VALUE = 1\n"))
    finding = RuleFinding(
        rule_id="QUALITY-LINT-001",
        title="Touched-file lint failed",
        severity=Severity.HIGH,
        metadata={"failing_collectors": ["oversized-module-soft: 1"]},
    )

    hint = quality_lint_hint(ctx, finding)

    assert "code-hygiene-refactor" in hint, (
        "public quality lint hint should route oversized collectors to recovery skill"
    )
    assert "slopgate lint check" in hint, (
        "public quality lint hint should keep repo-root lint verification guidance"
    )


def test_thin_wrapper_reason_lists_real_boundary_allowlist(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    content = "def target(value):\n    return value\n\n\ndef wrap(value):\n    return target(value)\n"
    result = evaluate_payload(write_payload(tmp_path, "src/wrap.py", content))
    support.assert_denied_by(result, "PY-CODE-013")
    context = additional_context(result)
    assert "validates/normalizes" in context
    _assert_boundary_allowlist_context(context)


def test_long_params_reason_is_role_aware_for_test_helpers(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    content = "def make_case(name, value, expected, mode, flag, retries, timeout):\n    return (name, value, expected, mode, flag, retries, timeout)\n"
    result = evaluate_payload(write_payload(tmp_path, "tests/test_cases.py", content))
    support.assert_denied_by(result, "PY-CODE-009")
    context = additional_context(result)
    assert "helper is pretending to be a constructor" in context
    assert "Case dataclass" in context
    assert "builder defaults" in context


def test_long_params_reason_is_role_aware_for_production_code(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    content = "def build(name, value, expected, mode, flag, retries, timeout):\n    return (name, value, expected, mode, flag, retries, timeout)\n"
    result = evaluate_payload(write_payload(tmp_path, "src/params.py", content))
    support.assert_denied_by(result, "PY-CODE-009")
    context = additional_context(result)
    assert "group by semantic meaning" in context
    assert "not arbitrary parameter bags" in context


def test_repo_prompt_context_preflights_hot_rules(bundle_root: Path) -> None:
    prompt_context = (
        bundle_root / "src" / "slopgate" / "resources" / "prompt_context" / "repo.md"
    ).read_text(encoding="utf-8")
    assert "Hot Hook Preflight" in prompt_context
    _assert_hot_prompt_preflight(prompt_context)


def test_context_only_hot_rules_say_advisory_not_retry_now(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    import_fanout = (
        "from math import sin, cos, tan, asin, acos, atan, sqrt, floor, ceil\n"
    )
    feature_envy = "service = object()\n\n\ndef render():\n    return (\n        service.alpha\n        + service.beta\n        + service.gamma\n        + service.delta\n        + service.epsilon\n        + service.zeta\n    )\n"
    import_result = evaluate_payload(
        write_payload(tmp_path, "src/imports.py", import_fanout)
    )
    envy_result = evaluate_payload(write_payload(tmp_path, "src/envy.py", feature_envy))
    assert any((item.rule_id == "PY-IMPORT-001" for item in import_result.findings))
    assert any((item.rule_id == "PY-CODE-012" for item in envy_result.findings))
    _assert_context_only_advisory(import_result, "PY-IMPORT-001")
    _assert_context_only_advisory(envy_result, "PY-CODE-012")
