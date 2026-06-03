"""Tests for regex rule target types beyond 'content'.

Covers: command, path, and prompt targets to verify RegexRule routing.
"""

from __future__ import annotations

from pathlib import Path

from tests import support
from tests.support import BUNDLE_ROOT, finding_ids
from vibeforcer.config import load_config
from vibeforcer.context import HookContext
from vibeforcer.engine import evaluate_payload
from vibeforcer.models import RegexRuleConfig
from vibeforcer.rules.regex_rule import RegexHit, RegexRule
from vibeforcer.state import HookStateStore
from vibeforcer.trace import TraceWriter
from vibeforcer.util.payloads import HookPayload


def bash_payload(command: str) -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(BUNDLE_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def regex_context(tmp_path: Path, payload: dict[str, object]) -> HookContext:
    config = load_config(tmp_path, ensure_enrollment=False, ensure_trace=False)
    trace = TraceWriter(tmp_path / ".vibeforcer" / "trace")
    return HookContext(
        payload=HookPayload(payload, config),
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def test_regex_rule_directly_evaluates_prompt_target(tmp_path: Path) -> None:
    rule = RegexRule(
        RegexRuleConfig(
            rule_id="PROMPT-TEST",
            title="Prompt test",
            target="prompt",
            patterns=["deploy"],
            events=["UserPromptSubmit"],
            message="{rule_id}:{matched_paths}",
        )
    )
    ctx = regex_context(
        tmp_path,
        {
            "session_id": "t",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "please deploy",
        },
    )

    findings = rule.evaluate(ctx)

    assert [(finding.rule_id, finding.message) for finding in findings] == [
        ("PROMPT-TEST", "PROMPT-TEST:")
    ]


def test_regex_hit_records_optional_path() -> None:
    assert RegexHit(path="src/app.py").path == "src/app.py"


class TestShellCommandTarget:
    """Shell hygiene regex rules match against bash_command."""

    def test_shell_set_plus_e_denied(self) -> None:
        result = evaluate_payload(bash_payload("set +e && make build"))
        assert "SHELL-001" in finding_ids(result), "set +e must trigger SHELL-001"

    def test_shell_stderr_suppression_gets_exact_repair_pattern(self) -> None:
        result = evaluate_payload(bash_payload("make build 2>/dev/null"))
        support.assert_denied_by(result, "SHELL-001")
        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )

        assert "`2>/dev/null`" in reason
        assert "if output=$(command 2>&1)" in reason

    def test_safe_command_no_shell_rule(self) -> None:
        result = evaluate_payload(bash_payload("npm test"))
        assert "SHELL-001" not in finding_ids(result), (
            "npm test must not trigger SHELL-001"
        )


class TestPythonShellEditCommandTarget:
    """Python shell-edit regex rules match command edit targets."""

    def test_py_shell_src_sed_edit_denied(self) -> None:
        result = evaluate_payload(bash_payload("sed -i 's/foo/bar/' src/main.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "sed -i on src/*.py must trigger PY-SHELL-001"
        )

    def test_py_shell_test_sed_edit_denied(self) -> None:
        result = evaluate_payload(
            bash_payload("sed -i 's/foo/bar/' tests/cli/test_signup_flow.py")
        )
        assert "PY-SHELL-001" in finding_ids(result), (
            "sed -i on tests/*.py must trigger PY-SHELL-001"
        )

    def test_py_shell_test_perl_edit_denied(self) -> None:
        command = "perl -i -p0e 's/foo/bar/gs' tests/cli/test_signup_flow.py"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" in finding_ids(result), (
            "perl -i on tests/*.py must trigger PY-SHELL-001"
        )

    def test_py_shell_cloud_sed_edit_denied(self) -> None:
        result = evaluate_payload(bash_payload("sed -i 's/foo/bar/' cloud/app/core.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "sed -i on Job Hunter cloud/*.py production code must trigger PY-SHELL-001"
        )

    def test_py_shell_automation_perl_edit_denied(self) -> None:
        command = "perl -pi -e 's/foo/bar/g' automation/scripts/eval/cli.py"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" in finding_ids(result), (
            "perl -pi on Job Hunter automation/*.py production code must trigger PY-SHELL-001"
        )

    def test_py_shell_dev_tee_edit_denied(self) -> None:
        result = evaluate_payload(bash_payload("printf 'x = 1' | tee dev/scripts/tool.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "tee to dev/*.py must trigger PY-SHELL-001"
        )

    def test_py_shell_root_python_file_redirect_denied(self) -> None:
        result = evaluate_payload(bash_payload("python gen.py > setup-native-host.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "redirecting output to a root-level Python file must trigger PY-SHELL-001"
        )

    def test_sed_expression_mentions_python_but_edits_non_python_not_py_shell(self) -> None:
        command = "sed -i 's#cloud/app/core.py#cloud/app/main.py#' README.md"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" not in finding_ids(result), (
            "PY-SHELL-001 should target the edited file, not .py text inside a sed expression"
        )

    def test_py_shell_src_redirect_edit_denied(self) -> None:
        result = evaluate_payload(bash_payload("python gen.py > src/main.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "redirecting output to src/*.py must trigger PY-SHELL-001"
        )

    def test_py_shell_test_redirect_edit_denied(self) -> None:
        result = evaluate_payload(bash_payload("python gen.py > tests/test_main.py"))
        assert "PY-SHELL-001" in finding_ids(result), (
            "redirecting output to tests/*.py must trigger PY-SHELL-001"
        )


class TestSearchPipelineCommandTarget:
    """Search pipelines only trigger shell-edit rules when they edit Python files."""

    def test_rg_search_with_fallback_not_py_shell_edit(self) -> None:
        command = (
            "rg -n 'compensation_result' src/autopilot/graph/ -g '*.py' -l "
            "2>/dev/null || grep -rn 'compensation_result' "
            "src/autopilot/graph/ --include='*.py' -l"
        )
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" not in finding_ids(result), (
            "rg/grep searches over src/*.py are not shell edits"
        )

    def test_rg_output_redirect_to_results_not_py_shell_edit(self) -> None:
        command = "rg foo src/main.py > matches.txt"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" not in finding_ids(result), (
            "redirecting search output away from src/*.py is not a source edit"
        )

    def test_rg_pipeline_to_src_shell_edit_denied(self) -> None:
        command = "rg -l foo src/ -g '*.py' | xargs sed -i 's/foo/bar/'"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" in finding_ids(result), (
            "search pipelines feeding shell edit commands must trigger PY-SHELL-001"
        )

    def test_rg_pipeline_to_tests_shell_edit_denied(self) -> None:
        command = "rg -l foo tests/ -g '*.py' | xargs sed -i 's/foo/bar/'"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" in finding_ids(result), (
            "test search pipelines feeding shell edit commands must trigger PY-SHELL-001"
        )

    def test_rg_pipeline_to_shell_edit_denied(self) -> None:
        command = "rg -l foo src/ -g '*.py' | xargs sed -i 's/foo/bar/'"
        result = evaluate_payload(bash_payload(command))
        assert "PY-SHELL-001" in finding_ids(result), (
            "search pipelines feeding shell edit commands must trigger PY-SHELL-001"
        )


class TestGitCommandTarget:
    """Git command regex rules match against bash_command."""

    def test_git_commit_gets_context(self) -> None:
        result = evaluate_payload(bash_payload("git commit -m 'fix: thing'"))
        assert "GIT-002" in finding_ids(result), (
            "git commit must trigger GIT-002 context"
        )

    def test_git_no_verify_denial_gives_safe_commit_command(self) -> None:
        result = evaluate_payload(bash_payload("git commit --no-verify -m 'skip hooks'"))
        assert "GIT-001" in finding_ids(result)
        support.assert_denied_by(result, "GIT-001")
        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )
        assert "git commit -m" in reason
        assert "fix the hook/test failure" in reason


class TestPathTarget:
    """Regex rules with target=path match against candidate_paths."""

    @staticmethod
    def _write_payload(file_path: str) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "x = 1\n"},
        }

    def test_linter_config_path_denied(self) -> None:
        result = evaluate_payload(self._write_payload(".pylintrc"))
        assert "PY-LINTER-001" in finding_ids(result), (
            ".pylintrc must trigger PY-LINTER-001"
        )

    def test_quality_test_path_denied(self) -> None:
        result = evaluate_payload(self._write_payload("tests/quality/test_new.py"))
        ids = finding_ids(result)
        matched = "QA-PATH-003" in ids or "BUILTIN-PROTECTED-PATHS" in ids
        assert matched, "tests/quality/ path must be flagged"

    def test_quality_path_denial_names_baseline_escape_hatch(self) -> None:
        result = evaluate_payload(self._write_payload("tests/quality/test_new.py"))
        qa_finding = next(
            finding for finding in result.findings if finding.rule_id == "QA-PATH-003"
        )
        combined = "\n".join(
            part for part in [qa_finding.message, qa_finding.additional_context] if part
        )

        assert "src/vibeforcer" in combined
        assert "tests/quality/baselines.json" in combined
        assert "python -m pytest -q tests/quality" in combined

    def test_fe_linter_config_denied(self) -> None:
        result = evaluate_payload(self._write_payload(".eslintrc.json"))
        ids = finding_ids(result)
        matched = "FE-LINTER-001" in ids or "BUILTIN-PROTECTED-PATHS" in ids
        assert matched, ".eslintrc.json must be flagged"

    def test_normal_path_not_flagged(self) -> None:
        result = evaluate_payload(self._write_payload("src/utils/helpers.py"))
        path_rules = {"PY-LINTER-001", "FE-LINTER-001", "QA-PATH-001", "QA-PATH-003"}
        assert not (finding_ids(result) & path_rules), (
            "normal path must not trigger path rules"
        )


class TestBaselineWarnPath:
    """WARN-BASELINE-001 fires on baselines.json path access."""

    def test_baselines_json_flagged(self) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "baselines.json",
                "content": '{"rules": {}}',
            },
        }
        result = evaluate_payload(payload)
        ids = finding_ids(result)
        matched = "WARN-BASELINE-001" in ids or "BASELINE-001" in ids
        assert matched, "baselines.json must trigger baseline warning"
