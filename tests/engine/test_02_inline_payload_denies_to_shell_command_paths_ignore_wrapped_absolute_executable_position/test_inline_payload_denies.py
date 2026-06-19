from __future__ import annotations

from slopgate._types import object_dict, string_value
from tests.test_engine import (
    BashBuilder,
    Path,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    pytest,
)

_PI_TYPE_SUPPRESSION_REASON_PREFIX = (
    "[PY-TYPE-002 | HIGH] Python type or lint suppression comments "
    "(# type: ignore, # noqa, # pylint: disable, # pyright: ignore, "
    "# ty: ignore) are blocked. Fix the underlying typing or lint issue instead."
)
_PI_USER_BASH_CONTEXT = (
    "Hook phase: PreToolUse; tool: Bash; failure class: quality; "
    "target: src/example.py.\n\nNext step: remove the suppression and add a "
    "Protocol, TypedDict, overload, or local stub."
)


class TestInlinePayloadDenies:
    @pytest.mark.parametrize(
        "command",
        [
            'git commit -n -m "skip"',
            "git commit -n",
            'git commit -m "skip" -n',
            'git commit -an -m "skip"',
        ],
    )
    def test_git_n_shorthand(self, pretool_bash: BashBuilder, command: str) -> None:
        result = evaluate_payload(pretool_bash(command))
        assert_denied_by(result, "GIT-001")
        assert "GIT-001" in finding_ids(result), (
            f"git no-verify shorthand should remain blocked for {command!r}"
        )

    def test_patch_with_any(self, bundle_root: Path) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "PreToolUse",
            "tool_name": "Patch",
            "tool_input": {
                "patch": "*** Update File: src/example.py\n+from typing import Any\n"
            },
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-TYPE-001")
        assert "PY-TYPE-001" in finding_ids(result), (
            "Patch payloads adding Any imports should remain blocked"
        )

    def test_python_shell_write_type_suppression_is_denied(
        self, pretool_bash: BashBuilder
    ) -> None:
        command = (
            'python -c "from pathlib import Path; '
            "Path('src/example.py').write_text('x = y  # type: ignore[arg-type]')\""
        )
        result = evaluate_payload(pretool_bash(command))

        assert_denied_by(result, "PY-TYPE-002")
        assert "PY-TYPE-002" in finding_ids(result), (
            "Python shell writes should not bypass suppression bans"
        )

    def test_pi_user_bash_python_write_type_suppression_is_denied(
        self, bundle_root: Path
    ) -> None:
        command = (
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "Path('src/example.py').write_text('x = y  # pyright: ignore[reportAny]')\n"
            "PY"
        )
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "user_bash",
            "command": command,
        }
        result = evaluate_payload(payload, platform="pi")

        assert "PY-TYPE-002" in finding_ids(result), (
            "Pi user_bash Python writes should not bypass suppression bans"
        )
        output = object_dict(result.output)
        reason = string_value(output.get("reason")) or ""
        assert output == {
            "block": True,
            "context": _PI_USER_BASH_CONTEXT,
            "reason": reason,
        }, "Pi user_bash denials should render block output with exact context"
        assert reason.startswith(_PI_TYPE_SUPPRESSION_REASON_PREFIX), (
            "Pi user_bash denial reason should start with the type-suppression rule"
        )

    def test_python_shell_read_suppression_search_is_allowed(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("rg '# type: ignore' src/example.py"))

        assert "PY-TYPE-002" not in finding_ids(result)
        assert_not_denied(result)

    def test_python_shell_write_without_suppression_is_allowed(
        self, pretool_bash: BashBuilder
    ) -> None:
        command = (
            'python -c "from pathlib import Path; '
            "Path('src/example.py').write_text('x: int = 1')\""
        )
        result = evaluate_payload(pretool_bash(command))

        assert "PY-TYPE-002" not in finding_ids(result)
        assert_not_denied(result)

    def test_shell_heredoc_write_type_suppression_is_denied(
        self, pretool_bash: BashBuilder
    ) -> None:
        command = "cat > src/example.py <<'PY'\nx = y  # type: ignore[arg-type]\nPY"
        result = evaluate_payload(pretool_bash(command))

        assert_denied_by(result, "PY-TYPE-002")
        assert "PY-TYPE-002" in finding_ids(result)

    def test_shell_tee_heredoc_write_type_suppression_is_denied(
        self, pretool_bash: BashBuilder
    ) -> None:
        command = (
            "cat <<'PY' | tee src/example.py\nx = y  # pyright: ignore[reportAny]\nPY"
        )
        result = evaluate_payload(pretool_bash(command))

        assert_denied_by(result, "PY-TYPE-002")
        assert "PY-TYPE-002" in finding_ids(result)

    def test_shell_echo_write_any_is_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash("echo 'from typing import Any' > src/example.py")
        )

        assert_denied_by(result, "PY-TYPE-001")
        assert "PY-TYPE-001" in finding_ids(result)

    def test_python_open_write_any_is_denied(self, pretool_bash: BashBuilder) -> None:
        command = (
            "python -c \"open('src/example.py', 'w').write('from typing import Any')\""
        )
        result = evaluate_payload(pretool_bash(command))

        assert_denied_by(result, "PY-TYPE-001")
        assert "PY-TYPE-001" in finding_ids(result)

    def test_ctx_execute_python_code_filters_code_smells(
        self, bundle_root: Path
    ) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "PreToolUse",
            "tool_name": "ctx_execute",
            "tool_input": {
                "language": "python",
                "code": "def get_all_users():\n    return UserRepository.find_all()\n",
            },
        }
        result = evaluate_payload(payload)

        assert_denied_by(result, "PY-CODE-013")
        assert "PY-CODE-013" in finding_ids(result)

    def test_ctx_execute_file_uses_path_for_code_smells(
        self, bundle_root: Path
    ) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "PreToolUse",
            "tool_name": "ctx_execute_file",
            "tool_input": {
                "path": "src/context_mode_example.py",
                "language": "python",
                "code": "def get_all_users():\n    return UserRepository.find_all()\n",
            },
        }
        result = evaluate_payload(payload)

        finding = next(
            (item for item in result.findings if item.rule_id == "PY-CODE-013"),
            None,
        )
        assert finding is not None, "Expected ctx_execute_file code smell finding"
        assert finding.metadata.get("path") == "src/context_mode_example.py"

    def test_ctx_execute_javascript_does_not_run_python_code_smells(
        self, bundle_root: Path
    ) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "PreToolUse",
            "tool_name": "ctx_execute",
            "tool_input": {
                "language": "javascript",
                "code": "function getAllUsers() { return UserRepository.findAll(); }\n",
            },
        }
        result = evaluate_payload(payload)

        assert "PY-CODE-013" not in finding_ids(result)
        assert_not_denied(result)

    def test_multiedit_second_edit_caught(self, bundle_root: Path) -> None:
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {"file_path": "src/a.py", "new_string": "x: int = 1"},
                    {"file_path": "src/b.py", "new_string": "from typing import Any"},
                ]
            },
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-TYPE-001", "Any")
        assert "PY-TYPE-001" in finding_ids(result), (
            "MultiEdit payloads should inspect later edits for Any imports"
        )
