from __future__ import annotations

import os

from tests.support import SKIP_UNIX_ONLY
from tests.test_engine import (
    BUNDLE_ROOT,
    BashBuilder,
    Path,
    WriteBuilder,
    assert_asked_by,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    finding_ids,
    pytest,
)


def test_protected_path_makefile(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("Makefile", "all:\n\techo hi\n"))
    assert_asked_by(result, "BUILTIN-PROTECTED-PATHS", "Makefile")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "direct Makefile writes should remain protected"
    )


def test_protected_path_pytest_ini(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("pytest.ini", "[pytest]\n"))
    assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
    assert "PY-LINTER-001" in finding_ids(result), (
        "pytest.ini writes should trigger the linter-config rule"
    )


@pytest.mark.parametrize(
    ("event_name", "file_path"),
    [
        ("PreToolUse", "pytest.ini"),
        ("PreToolUse", "Makefile"),
        ("PermissionRequest", "Makefile"),
    ],
)
def test_protected_path_reads_are_allowed(
    bundle_root: Path, event_name: str, file_path: str
) -> None:
    result = evaluate_payload(
        {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": event_name,
            "tool_name": "Read",
            "tool_input": {"file_path": file_path},
        }
    )
    assert_not_denied(result)
    assert "BUILTIN-PROTECTED-PATHS" not in finding_ids(result), (
        f"{event_name} reads of {file_path} should remain allowed"
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "str_replace_editor",
        "morph_edit_file",
        "replace",
        "serena_replace_symbol_body",
    ],
)
def test_linter_config_edit_like_aliases_are_denied(tool_name: str) -> None:
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


def test_linter_config_read_allowed(bundle_root: Path) -> None:
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
    assert "PY-LINTER-001" not in finding_ids(result), (
        "ruff.toml reads should not trigger linter config edit protection"
    )


def test_protected_staging_rule_file_denied(pretool_write: WriteBuilder) -> None:
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


@SKIP_UNIX_ONLY
def test_system_path(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("/etc/passwd", "x"))
    assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
    assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
        "direct writes to protected system paths should remain blocked"
    )


@SKIP_UNIX_ONLY
def test_system_path_relative_escape(pretool_bash: BashBuilder, tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "d"
    nested.mkdir(parents=True)
    escape_target = os.path.relpath("/etc/passwd", nested.resolve())
    result = evaluate_payload(pretool_bash(f"cat {escape_target}", cwd=str(nested)))
    assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
    assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
        "relative escapes to protected system paths should remain denied"
    )


def test_absolute_search_executable_path_is_not_system_path_target(
    pretool_bash: BashBuilder,
) -> None:
    result = evaluate_payload(pretool_bash('/usr/bin/rg -n "needle" src'))
    assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result), (
        "absolute search executables should not be treated as target files"
    )


def test_absolute_find_executable_after_shell_separator_is_not_system_path_target(
    pretool_bash: BashBuilder,
) -> None:
    result = evaluate_payload(pretool_bash("cd src && /usr/bin/find . -name '*.py'"))
    assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" not in finding_ids(result), (
        "absolute find executables after separators should not be target files"
    )


def test_system_path_argument_still_denied(pretool_bash: BashBuilder) -> None:
    result = evaluate_payload(pretool_bash("cat /usr/bin/rg"))
    assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
    assert "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in finding_ids(result), (
        "protected executable paths used as file arguments should remain denied"
    )


def test_sensitive_data(pretool_bash: BashBuilder) -> None:
    result = evaluate_payload(pretool_bash("cat ~/.ssh/id_rsa"))
    assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")
    assert "GLOBAL-BUILTIN-SENSITIVE-DATA" in finding_ids(result), (
        "Bash reads of private key paths should remain blocked"
    )


def test_exec_protection_bash_write(pretool_bash: BashBuilder) -> None:
    result = evaluate_payload(pretool_bash("echo x > .claude/hooks/run-pretool.sh"))
    assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "Bash writes to hook scripts should remain protected"
    )


def test_exec_protection_bash_redirect_without_spaces(
    pretool_bash: BashBuilder,
) -> None:
    result = evaluate_payload(pretool_bash("grep foo src/app.py>pyproject.toml"))
    assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "redirections into protected config paths should remain denied"
    )


def test_exec_protection_bash_touch_makefile(pretool_bash: BashBuilder) -> None:
    result = evaluate_payload(pretool_bash("touch Makefile"))
    assert_asked_by(result, "BUILTIN-PROTECTED-PATHS")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "Bash writes to protected Makefile paths should remain protected"
    )


def test_exec_protection_write_config(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write(".claude/hook-layer/config.json", "{}"))
    assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "direct writes to hook-layer config should remain protected"
    )


def test_exec_protection_bash_write_staging_rule(pretool_bash: BashBuilder) -> None:
    result = evaluate_payload(
        pretool_bash(
            "echo '# temp' > src/slopgate/rules/python_ast/_staging/test_smell_rules.py"
        )
    )
    assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        "Bash writes to protected staging rule files should remain denied"
    )


def test_security_bypass_permissions(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(
        pretool_write("src/settings.py", "BYPASS_PERMISSIONS = True\n")
    )
    assert_denied_by(result, "BUILTIN-RULEBOOK-SECURITY", "bypass")
    assert "BUILTIN-RULEBOOK-SECURITY" in finding_ids(result), (
        "permission bypass constants should remain blocked"
    )
