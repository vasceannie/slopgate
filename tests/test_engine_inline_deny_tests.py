"""Inline payload deny tests — split from test_engine.py to keep module size under limit."""
from __future__ import annotations

import pytest

from tests.test_engine import (
    MonkeyPatch,
    Path,
    WriteBuilder,
    BashBuilder,
    EngineResult,
    assert_denied_by,
    evaluate_payload,
    finding_ids,
    _write_config_from_defaults,
    _keep_default_config,
)


def _assert_protected_path_asks(result: EngineResult) -> None:
    output = getattr(result, "output", None) or {}
    hook_specific = output.get("hookSpecificOutput")
    assert isinstance(hook_specific, dict)
    assert hook_specific.get("permissionDecision") == "ask"
    reason = str(hook_specific.get("permissionDecisionReason") or "")
    assert "BUILTIN-PROTECTED-PATHS" in reason
    assert "explicit approval" in reason.lower()
    assert any(f.rule_id == "BUILTIN-PROTECTED-PATHS" for f in result.findings)


class TestInlinePayloadDenies:

    def test_default_claude_control_plane_markdown_denied(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(tmp_path, monkeypatch, _keep_default_config)
        result = evaluate_payload(
            pretool_write(
                ".claude/CLAUDE.md",
                "# local control plane\n",
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
        assert any(f.rule_id == "BUILTIN-PROTECTED-PATHS" for f in result.findings)

    def test_broad_claude_protection_allows_claude_worktree_content(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(
            tmp_path,
            monkeypatch,
            lambda defaults: defaults.update({"protected_paths": [".claude/", "Makefile"]}),
        )
        result = evaluate_payload(
            pretool_write(
                ".claude/worktrees/feature/src/app.py",
                "from __future__ import annotations\n",
            )
        )
        assert all(f.rule_id != "BUILTIN-PROTECTED-PATHS" for f in result.findings)

    def test_broad_claude_protection_still_denies_normal_claude_content(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(
            tmp_path,
            monkeypatch,
            lambda defaults: defaults.update({"protected_paths": [".claude/", "Makefile"]}),
        )
        result = evaluate_payload(
            pretool_write(
                ".claude/CLAUDE.md",
                "# local control plane\n",
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
        assert any(f.rule_id == "BUILTIN-PROTECTED-PATHS" for f in result.findings)

    def test_default_claude_protection_allows_plan_markdown(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(tmp_path, monkeypatch, _keep_default_config)
        result = evaluate_payload(
            pretool_write(
                "/home/trav/.claude/plans/review-my-logs-and-partitioned-charm.md",
                "# Plan\n\n- inspect logs\n",
            )
        )
        assert all(f.rule_id != "BUILTIN-PROTECTED-PATHS" for f in result.findings)

    def test_default_claude_protection_denies_non_markdown_plan_file(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(tmp_path, monkeypatch, _keep_default_config)
        result = evaluate_payload(
            pretool_write(
                "/home/trav/.claude/plans/not-a-plan.json",
                "{}\n",
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")
        assert any(f.rule_id == "BUILTIN-PROTECTED-PATHS" for f in result.findings)

    def test_broad_claude_protection_asks_for_makefile_edits_in_worktrees(
        self,
        pretool_write: WriteBuilder,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        _write_config_from_defaults(
            tmp_path,
            monkeypatch,
            lambda defaults: defaults.update({"protected_paths": [".claude/", "Makefile"]}),
        )
        result = evaluate_payload(
            pretool_write(
                ".claude/worktrees/feature/Makefile",
                "all:\n\techo hi\n",
            )
        )
        assert result.findings
        _assert_protected_path_asks(result)

    def test_protected_rule_discovery_allows_readonly_bash_with_dev_null_redirects(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_bash(
                "cd /home/trav\n"
                "echo '===== slopgate config tree ====='\n"
                "find ~/.config/slopgate -maxdepth 2 -type f 2>/dev/null | head -40\n"
                "echo ''\n"
                "echo '===== grep PY-LOG-002 across config + rules ====='\n"
                "rg -l 'PY-LOG-002|boundary' ~/.config/slopgate ~/.claude/rules "
                "~/.claude/subagent-rules 2>/dev/null | head -20"
            )
        )
        ids = finding_ids(result)
        assert "BUILTIN-PROTECTED-PATHS" not in ids
        assert "GLOBAL-BUILTIN-HOOK-INFRA-EXEC" not in ids

    def test_protected_rule_discovery_allows_plain_rg_read(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_bash("rg -n 'PY-LOG-002|boundary' ~/.claude/rules 2>/dev/null")
        )
        assert "BUILTIN-PROTECTED-PATHS" not in finding_ids(result)

    def test_exec_protection_still_denies_writing_protected_rule_path_with_redirect(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("rg boundary src > ~/.claude/rules/boundary.md"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")
        assert any(f.rule_id == "BUILTIN-PROTECTED-PATHS" for f in result.findings)


def test_powershell_git_no_verify_denied(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
        encoding="utf-8",
    )
    payload = {
        "session_id": "ps-git",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "PowerShell",
        "tool_input": {"command": "git commit --no-verify -m 'skip'"},
    }
    result = evaluate_payload(payload)
    assert_denied_by(result, "GIT-001")
    assert any(f.rule_id == "GIT-001" for f in result.findings)


def test_powershell_windows_system_path_denied(tmp_path: Path) -> None:
    payload = {
        "session_id": "ps-system",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "PowerShell",
        "tool_input": {"command": r"Get-Content C:\Windows\System32\drivers\etc\hosts"},
    }
    result = evaluate_payload(payload)
    assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")
    assert any(f.rule_id == "GLOBAL-BUILTIN-SYSTEM-PROTECTION" for f in result.findings)


@pytest.mark.parametrize(
    ("command", "rule_id"),
    (
        ("Set-Content -Path pyproject.toml -Value x", "BUILTIN-PROTECTED-PATHS"),
        (r"Set-Content -Path .\pyproject.toml -Value x", "BUILTIN-PROTECTED-PATHS"),
        (
            r"Out-File -FilePath C:\Windows\System32\drivers\etc\hosts",
            "GLOBAL-BUILTIN-SYSTEM-PROTECTION",
        ),
        (
            r"Remove-Item -LiteralPath .\tests\quality\policy.py",
            "BUILTIN-PROTECTED-PATHS",
        ),
    ),
)
def test_powershell_path_commands_are_evaluated_through_rules(
    tmp_path: Path, command: str, rule_id: str
) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
        encoding="utf-8",
    )
    payload = {
        "session_id": "ps-protected",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "PowerShell",
        "tool_input": {"command": command},
    }
    result = evaluate_payload(payload)
    assert_denied_by(result, rule_id)
    assert any(f.rule_id == rule_id for f in result.findings)
