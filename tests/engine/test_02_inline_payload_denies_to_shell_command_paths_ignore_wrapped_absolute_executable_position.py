from __future__ import annotations

from tests.test_engine import (
    BUNDLE_ROOT,
    BashBuilder,
    Path,
    WriteBuilder,
    assert_denied_by,
    assert_not_denied,
    assert_asked_by,
    evaluate_payload,
    finding_ids,
    pytest,
    shell_command_paths,
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

    def test_protected_path_makefile(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("Makefile", "all:\n\techo hi\n"))
        assert_asked_by(result, "BUILTIN-PROTECTED-PATHS", "Makefile")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "direct Makefile writes should remain protected"
        )

    def test_protected_path_pytest_ini(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("pytest.ini", "[pytest]\n"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
        assert "PY-LINTER-001" in finding_ids(result)

    def test_protected_path_pytest_ini_read_allowed(self, bundle_root: Path) -> None:
        result = evaluate_payload(
            {
                "session_id": "t",
                "cwd": str(bundle_root),
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "pytest.ini"},
            }
        )
        assert_not_denied(result)
        assert "BUILTIN-PROTECTED-PATHS" not in finding_ids(result)

    @pytest.mark.parametrize(
        "tool_name",
        [
            "str_replace_editor",
            "morph_edit_file",
            "serena_replace_symbol_body",
        ],
    )
    def test_linter_config_edit_like_aliases_are_denied(self, tool_name: str) -> None:
        result = evaluate_payload(
            {
                "session_id": "t",
                "cwd": str(BUNDLE_ROOT),
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {
                    "file_path": "ruff.toml",
                    "content": "line-length = 120\n",
                },
            }
        )

        assert_denied_by(result, "PY-LINTER-001")
        assert "PY-LINTER-001" in finding_ids(result), (
            "edit-like alias tools should be denied for protected linter config edits"
        )

    def test_linter_config_read_allowed(self, bundle_root: Path) -> None:
        result = evaluate_payload(
            {
                "session_id": "t",
                "cwd": str(bundle_root),
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "ruff.toml"},
            }
        )

        assert_not_denied(result)
        assert "PY-LINTER-001" not in finding_ids(result)

    def test_protected_staging_rule_file_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_write(
                "src/slopgate/rules/python_ast/_staging/duplicate_rules.py",
                "from __future__ import annotations\n",
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "protected staging rule files should remain blocked"
        )

    def test_system_path(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("/etc/passwd", "x"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
            "direct writes to protected system paths should remain blocked"
        )

    def test_system_path_relative_escape(
        self, pretool_bash: BashBuilder, tmp_path: Path
    ) -> None:
        nested = tmp_path / "a" / "b" / "c" / "d"
        nested.mkdir(parents=True)
        result = evaluate_payload(
            pretool_bash("cat ../../../../../../../../etc/passwd", cwd=str(nested))
        )
        assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
            "relative escapes to protected system paths should remain denied"
        )

    def test_absolute_search_executable_path_is_not_system_path_target(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash('/usr/bin/rg -n "needle" src'))
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result)

    def test_absolute_find_executable_after_shell_separator_is_not_system_path_target(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_bash("cd src && /usr/bin/find . -name '*.py'")
        )
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result)

    def test_system_path_argument_still_denied(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat /usr/bin/rg"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
        assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
            "protected executable paths used as file arguments should remain denied"
        )

    def test_sensitive_data(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat ~/.ssh/id_rsa"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
        assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
            "Bash reads of private key paths should remain blocked"
        )

    def test_exec_protection_bash_write(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("echo x > .claude/hooks/run-pretool.sh"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "Bash writes to hook scripts should remain protected"
        )

    def test_exec_protection_bash_redirect_without_spaces(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("grep foo src/app.py>pyproject.toml"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "redirections into protected config paths should remain denied"
        )

    def test_exec_protection_bash_touch_makefile(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("touch Makefile"))
        assert_asked_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "Bash writes to protected Makefile paths should remain protected"
        )

    def test_exec_protection_write_config(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write(".claude/hook-layer/config.json", "{}"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "direct writes to hook-layer config should remain protected"
        )

    def test_exec_protection_bash_write_staging_rule(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_bash(
                "echo '# temp' > src/slopgate/rules/python_ast/_staging/test_smell_rules.py"
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
            "Bash writes to protected staging rule files should remain denied"
        )

    def test_security_bypass_permissions(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(
            pretool_write("src/settings.py", "BYPASS_PERMISSIONS = True\n")
        )
        assert_denied_by(result, "BUILTIN-RULEBOOK-SECURITY", "bypass")
        assert "BUILTIN-RULEBOOK-SECURITY" in finding_ids(result), (
            "permission bypass constants should remain blocked"
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


def test_shell_command_paths_captures_redirect_targets() -> None:
    paths = shell_command_paths(
        "grep foo src/app.py>pyproject.toml && echo hi > Makefile && touch Makefile"
    )
    assert "pyproject.toml" in paths
    assert "Makefile" in paths


def test_shell_command_paths_ignores_glob_patterns() -> None:
    paths = shell_command_paths("python -m py_compile *.py src/*.py")
    assert "*.py" not in paths
    assert "src/*.py" not in paths


def test_shell_command_paths_ignores_paths_inside_quoted_option_text() -> None:
    paths = shell_command_paths(
        'bd close job-hunter-6vc1 --reason="Centralized parsing in '
        "src/sse_parsing.py and cloud agent_stream/sse.py; moved "
        'runtime_lifecycle.py."'
    )
    assert "src/sse_parsing.py" not in paths
    assert "agent_stream/sse.py" not in paths
    assert "runtime_lifecycle.py" not in paths


def test_shell_command_paths_still_captures_path_option_values() -> None:
    paths = shell_command_paths("tool --config=pyproject.toml --file src/app.py")
    assert "pyproject.toml" in paths
    assert "src/app.py" in paths


def test_shell_command_paths_ignore_absolute_executable_position() -> None:
    paths = shell_command_paths('/usr/bin/rg -n "needle" src/app.py')
    assert "/usr/bin/rg" not in paths
    assert "src/app.py" in paths


def test_shell_command_paths_ignore_wrapped_absolute_executable_position() -> None:
    paths = shell_command_paths(
        "env FOO=bar /usr/bin/python -m pytest tests/test_app.py"
    )
    assert "/usr/bin/python" not in paths
    assert "tests/test_app.py" in paths
