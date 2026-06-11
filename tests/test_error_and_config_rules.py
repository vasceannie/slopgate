"""Tests for ERRORS-BASH-001, ERRORS-FAIL-001, and CONFIG-001 rules."""

from __future__ import annotations

import pytest

from slopgate.engine import evaluate_payload
from slopgate.rules.error_rules import BashFailureReinforcementRule, BashOutputErrorRule
from tests.support import BUNDLE_ROOT, SKIP_UNIX_ONLY, finding_ids, hook_output, required_string


class TestBashOutputError:
    """ERRORS-BASH-001: detect errors in exit-0 bash output."""

    def test_rule_classes_keep_stable_rule_ids(self) -> None:
        assert {
            BashOutputErrorRule.rule_id,
            BashFailureReinforcementRule.rule_id,
        } == {"ERRORS-BASH-001", "ERRORS-FAIL-001"}

    @staticmethod
    def _post_bash(
        command: str,
        stdout: str,
        stderr: str = "",
    ) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {
                "stdout": stdout,
                "stderr": stderr,
                "exitCode": 0,
            },
        }

    def test_traceback_detected(self) -> None:
        payload = self._post_bash(
            "python run.py",
            "Traceback (most recent call last):\n  File 'run.py'\nValueError: bad\nValueError: also bad",
        )
        result = evaluate_payload(payload)
        assert "ERRORS-BASH-001" in finding_ids(result), (
            "traceback in output must trigger error rule"
        )

    def test_test_failure_detected(self) -> None:
        payload = self._post_bash(
            "pytest tests/",
            "FAILED tests/test_auth.py::test_login - AssertionError\n1 failed, 5 passed",
        )
        result = evaluate_payload(payload)
        assert "ERRORS-BASH-001" in finding_ids(result), (
            "test failures must trigger error rule"
        )

    def test_test_failure_context_names_trigger_and_next_action(self) -> None:
        payload = self._post_bash(
            "pytest tests/",
            "FAILED tests/test_auth.py::test_login - AssertionError\n1 failed, 5 passed",
        )
        result = evaluate_payload(payload)
        message = required_string(hook_output(result), "additionalContext")
        assert "ERRORS-BASH-001" in message, "context should name the bash-output rule"
        assert "pytest tests/" in message, "context should echo the failing command"
        assert "error-like output even though the command exited 0" in message, (
            "context should explain the exit-0 failure shape"
        )
        assert "Rerun the smallest failing command" in message, (
            "context should include the next repair action"
        )


class TestBashFailureReinforcement:
    """ERRORS-FAIL-001: reinforce that non-zero exits must be resolved."""

    @staticmethod
    def _failure_bash(command: str) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": "", "stderr": "error", "exitCode": 1},
        }

    def test_build_failure_triggers(self) -> None:
        result = evaluate_payload(self._failure_bash("make build"))
        assert "ERRORS-FAIL-001" in finding_ids(result), (
            "non-zero exit on build must trigger"
        )

    def test_build_failure_context_names_trigger_and_next_action(self) -> None:
        result = evaluate_payload(self._failure_bash("make build"))
        message = required_string(result.output or {}, "systemMessage")
        assert "ERRORS-FAIL-001" in message, (
            "system message should name the failure rule"
        )
        assert "make build" in message, "system message should echo the failing command"
        assert "exited non-zero" in message, (
            "system message should explain the failure trigger"
        )
        assert "Inspect stdout/stderr" in message, (
            "system message should include the next action"
        )
        assert "pre-existing" not in message, (
            "failure context should avoid STOP-001 banned provenance language"
        )
        assert "out of scope" not in message, (
            "failure context should avoid STOP-001 banned scope language"
        )

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("grep pattern file.txt", id="grep_no_match"),
            pytest.param("rg pattern src", id="rg_no_match"),
            pytest.param("rtk rg pattern src", id="rtk_rg_no_match"),
        ],
    )
    def test_search_no_match_failure_skipped(self, command: str) -> None:
        result = evaluate_payload(self._failure_bash(command))
        assert "ERRORS-FAIL-001" not in finding_ids(result), (
            f"{command} exit-1 should be treated as expected search semantics"
        )

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("diff a.txt b.txt", id="diff_difference"),
            pytest.param("test -f missing.txt", id="test_false"),
        ],
    )
    def test_expected_probe_failure_skipped(self, command: str) -> None:
        result = evaluate_payload(self._failure_bash(command))
        assert "ERRORS-FAIL-001" not in finding_ids(result), (
            f"{command} exit-1 should be treated as expected command semantics"
        )

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("command -v missing-tool", id="command_probe_miss"),
            pytest.param("git diff --exit-code", id="git_diff_changes"),
        ],
    )
    def test_expected_tool_probe_failure_skipped(self, command: str) -> None:
        result = evaluate_payload(self._failure_bash(command))
        assert "ERRORS-FAIL-001" not in finding_ids(result), (
            f"{command} exit-1 should be treated as expected command semantics"
        )

    def test_cat_failure_skipped(self) -> None:
        result = evaluate_payload(self._failure_bash("cat nonexistent.txt"))
        assert "ERRORS-FAIL-001" not in finding_ids(result), (
            "read-only failures are skipped"
        )

    def test_dev_null_stderr_suppression_reports_shell_rule_only(self) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": 'rg -l "RunSummaryEvent" -t py 2>/dev/null'},
        }
        result = evaluate_payload(payload)
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "SHELL-001" in reason
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in reason


class TestDevNullSystemProtection:
    """GLOBAL-BUILTIN-SYSTEM-PROTECTION: allow exact /dev/null only."""

    @staticmethod
    def _pre_bash(command: str) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

    @staticmethod
    def _pre_write(path: str) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        }

    def test_exact_dev_null_bash_reference_allowed(self) -> None:
        result = evaluate_payload(self._pre_bash("cat /dev/null"))
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result)

    def test_other_dev_paths_still_blocked_in_bash(self) -> None:
        result = evaluate_payload(self._pre_bash("cat /dev/sda"))
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result)

    def test_exact_dev_null_tool_path_allowed(self) -> None:
        result = evaluate_payload(self._pre_write("/dev/null"))
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result)

    @SKIP_UNIX_ONLY
    def test_other_dev_tool_paths_still_blocked(self) -> None:
        result = evaluate_payload(self._pre_write("/dev/sda"))
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result)


class TestConfigChangeGuard:
    """CONFIG-001: block config changes that weaken security."""

    @staticmethod
    def _config_change(
        source: str,
        changes: dict[str, object],
    ) -> dict[str, object]:
        return {
            "session_id": "t",
            "cwd": str(BUNDLE_ROOT),
            "hook_event_name": "ConfigChange",
            "source": source,
            "changes": changes,
        }

    def test_disable_all_hooks_blocked(self) -> None:
        payload = self._config_change("project_settings", {"disableAllHooks": True})
        result = evaluate_payload(payload)
        assert result.output is not None, "disableAllHooks must produce output"
        assert result.output.get("decision") == "block", (
            "disableAllHooks must be blocked"
        )

    def test_hook_modification_blocked(self) -> None:
        payload = self._config_change("local_settings", {"hooks": {"pre_tool_use": []}})
        result = evaluate_payload(payload)
        assert result.output is not None, "hook modification must produce output"
        assert result.output.get("decision") == "block", (
            "hook modification must be blocked"
        )

    def test_non_security_change_allowed(self) -> None:
        payload = self._config_change("project_settings", {"theme": "dark"})
        result = evaluate_payload(payload)
        decision = result.output.get("decision") if result.output is not None else None
        assert decision != "block", "non-security changes must not be blocked"

    def test_unknown_source_allowed(self) -> None:
        payload = self._config_change("policy_settings", {"disableAllHooks": True})
        result = evaluate_payload(payload)
        decision = result.output.get("decision") if result.output is not None else None
        assert decision != "block", "policy source must not be guarded"
