"""Hook-layer tests — pytest + conftest fixtures + parametrize.
All shared fixtures (evaluate, load_fixture, pretool_write, pretool_bash,
bundle_root, tmp_project) live in conftest.py. Shared non-fixture helpers
live in tests.support.
"""
from __future__ import annotations
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
import pytest
from pytest import MonkeyPatch
from vibeforcer._types import ObjectDict, object_dict
from vibeforcer.engine import evaluate_payload
from vibeforcer.models import EngineResult
from vibeforcer.util.payloads import shell_command_paths
from tests.support import (
    BUNDLE_ROOT,
    LoadFixture,
    WriteBuilder,
    BashBuilder,
    EvaluateFn,
    assert_blocked,
    assert_denied_by,
    assert_not_denied,
    finding_ids,
    hook_output,
    nested_output,
    output_string,
    require_output,
    required_string,
)
FIXTURE_FILE_NAMES = tuple(
    sorted(path.name for path in (BUNDLE_ROOT / "fixtures").glob("*.json"))
)
VIRTUALENV_PARSE_SKIP_PATHS = (
    ".venv/lib/python3.12/site-packages/pkg/bad.py",
    "venv/lib/python3.12/site-packages/pkg/bad.py",
    "env/lib/python3.12/site-packages/pkg/bad.py",
    "src/pkg/site-packages/vendor/bad.py",
)
def _fixture_output(
    load_fixture: LoadFixture, fixture_name: str
) -> tuple[str, ObjectDict | None]:
    fixture_path = BUNDLE_ROOT / "fixtures" / fixture_name
    data = object_dict(cast(object, json.loads(fixture_path.read_text())))
    event = output_string(data, "hook_event_name", "unknown")
    result = evaluate_payload(load_fixture(fixture_name))
    return event, result.output
def _disabled_rule_findings(
    load_fixture: LoadFixture, fixture_name: str, rule_id: str
) -> list[object]:
    from vibeforcer.config import load_config
    from vibeforcer.context import HookContext
    from vibeforcer.rules import build_rules
    from vibeforcer.state import HookStateStore
    from vibeforcer.trace import TraceWriter
    from vibeforcer.util.payloads import HookPayload
    payload = load_fixture(fixture_name)
    config = load_config()
    config.enabled_rules[rule_id] = False
    try:
        trace = TraceWriter(config.trace_dir)
        hp = HookPayload(payload, config)
        state = HookStateStore(config.trace_dir)
        ctx = HookContext(payload=hp, config=config, trace=trace, state=state)
        target_rule = next(
            (rule for rule in build_rules(ctx) if rule.rule_id == rule_id), None
        )
        assert target_rule is not None, f"Expected to find rule {rule_id}"
        return list(target_rule.evaluate(ctx))
    finally:
        config.enabled_rules[rule_id] = True
def _rule_build_context(load_fixture: LoadFixture) -> tuple[Any, object]:
    from vibeforcer.config import load_config
    from vibeforcer.context import HookContext
    import vibeforcer.rules as rules_mod
    from vibeforcer.state import HookStateStore
    from vibeforcer.trace import TraceWriter
    from vibeforcer.util.payloads import HookPayload
    config = load_config()
    trace = TraceWriter(config.trace_dir)
    state = HookStateStore(config.trace_dir)
    payload = HookPayload(load_fixture("pretool_git_no_verify.json"), config)
    ctx = HookContext(payload=payload, config=config, trace=trace, state=state)
    return rules_mod, ctx
def _write_quality_gate(
    repo: Path, content: str = "[quality_gate]\nenabled = true\n"
) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / "quality_gate.toml").write_text(content, encoding="utf-8")
    return repo
def _assert_worktree_marker_copied(repo: Path, worktree_marker: Path) -> None:
    assert worktree_marker.exists()
    assert worktree_marker.read_text(encoding="utf-8") == (repo / "quality_gate.toml").read_text(
        encoding="utf-8"
    )
def _write_config_from_defaults(
    tmp_path: Path, monkeypatch: MonkeyPatch, mutate: Callable[[dict[str, Any]], None]
) -> Path:
    defaults_path = BUNDLE_ROOT / "src" / "vibeforcer" / "resources" / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    mutate(defaults)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(defaults), encoding="utf-8")
    monkeypatch.setenv("VIBEFORCER_CONFIG", str(cfg))
    return cfg
def _enable_failing_post_edit_quality_command(defaults: dict[str, Any]) -> None:
    defaults["post_edit_quality"]["enabled"] = True
    defaults["post_edit_quality"]["block_on_failure"] = True
    defaults["post_edit_quality"]["commands_by_language"] = {"python": ["pwd && false"]}
def _disable_default_post_edit_quality(defaults: dict[str, Any]) -> None:
    defaults["post_edit_quality"]["enabled"] = False
def _keep_default_config(defaults: dict[str, Any]) -> None:
    _ = defaults
def _latest_trace_event(tmp_path: Path) -> ObjectDict:
    events = (tmp_path / "vf-root" / "logs" / "events.jsonl").read_text(
        encoding="utf-8"
    ).strip().splitlines()
    assert events
    return object_dict(json.loads(events[-1]))
def _set_skip_paths(defaults: dict[str, Any], repo: Path) -> None:
    defaults["skip_paths"] = [str(repo.resolve())]
def _write_skip_paths_config(tmp_path: Path, monkeypatch: MonkeyPatch, repo: Path) -> Path:
    def mutate(defaults: dict[str, Any]) -> None:
        _set_skip_paths(defaults, repo)
    return _write_config_from_defaults(tmp_path, monkeypatch, mutate)
def _post_edit_bash_payload(cwd: Path, command: str = "echo 'print(1)' > app.py") -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
def _evaluate_post_edit_bash(cwd: Path, command: str = "echo 'print(1)' > app.py") -> EngineResult:
    return evaluate_payload(_post_edit_bash_payload(cwd, command))
def _strict_rule_id_sets(repo: Path) -> tuple[set[str], set[str]]:
    from vibeforcer.adapters import get_adapter
    from vibeforcer.context import build_context
    from vibeforcer.rules import build_always_on_rules, build_repo_strict_rules
    ctx = build_context(
        get_adapter("claude").normalize_payload(
            _pretool_write_payload(repo, "src/app.py", "from typing import Any\n")
        )
    )
    return (
        {rule.rule_id for rule in build_always_on_rules(ctx)},
        {rule.rule_id for rule in build_repo_strict_rules(ctx)},
    )
def _repo_with_moved_parse_error(tmp_path: Path) -> Path:
    repo = tmp_path / "repo_move_ast_health"
    source_dir = repo / "src" / "pkg"
    target_dir = source_dir / "moved"
    target_dir.mkdir(parents=True)
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    old_path = source_dir / "worker.py"
    new_path = target_dir / "worker.py"
    _ = new_path.write_text("def worker(:\n    return 1\n", encoding="utf-8")
    assert not old_path.exists()
    assert new_path.exists()
    return repo
def _is_not_denied(result: EngineResult) -> bool:
    output = getattr(result, "output", None)
    if output is None:
        return True
    spec = object_dict(output.get("hookSpecificOutput"))
    return output_string(spec, "permissionDecision") != "deny"
def _assert_write_negative_case(
    pretool_write: WriteBuilder,
    file_path: str,
    content: str,
    forbidden_rule: str | None,
) -> tuple[bool, str]:
    result = evaluate_payload(pretool_write(file_path, content))
    ids = finding_ids(result)
    passes_expectation = (
        forbidden_rule not in ids
        if forbidden_rule is not None
        else _is_not_denied(result)
    )
    detail = (
        f"Unexpected deny state for {file_path}: forbidden_rule={forbidden_rule!r}, "
        f"ids={ids}, output={result.output!r}"
    )
    return passes_expectation, detail
def _assert_bash_negative_case(
    pretool_bash: BashBuilder,
    evaluate: EvaluateFn,
    command: str,
    forbidden_rule: str | None,
) -> tuple[bool, str]:
    result = evaluate(pretool_bash(command))
    ids = finding_ids(result)
    passes_expectation = (
        forbidden_rule not in ids
        if forbidden_rule is not None
        else _is_not_denied(result)
    )
    detail = (
        f"Unexpected deny state for command {command!r}: forbidden_rule={forbidden_rule!r}, "
        f"ids={ids}, output={result.output!r}"
    )
    return passes_expectation, detail


# ===========================================================================
# PreToolUse: parametrised positive deny tests (fixture-driven)
# ===========================================================================


@pytest.mark.parametrize(
    "fixture_name, rule_id, msg_fragment",
    [
        # BUILTIN-ENFORCE-FULL-READ is disabled in default config
        # ("pretool_read_partial.json", "BUILTIN-ENFORCE-FULL-READ", "in full first"),
        ("pretool_git_no_verify.json", "GIT-001", "hook bypass detected"),
        ("pretool_python_any.json", "PY-TYPE-001", "Any"),
        ("pretool_ts_ignore.json", "TS-LINT-002", "suppression"),
        ("pretool_rust_unwrap.json", "RS-QUALITY-002", "unwrap"),
        ("pretool_python_source_bash.json", "PY-SHELL-001", "shell edit"),
        ("pretool_datetime_fallback.json", "PY-QUALITY-004", "datetime.now"),
        ("pretool_silent_none.json", "PY-QUALITY-006", "None"),
        ("pretool_silent_except.json", "PY-EXC-002", "silent"),
        ("pretool_assertion_roulette.json", "PY-TEST-001", "assert"),
        ("pretool_python_todo.json", "PY-QUALITY-007", "TODO"),
        ("pretool_test_sleep.json", "PY-TEST-002", "sleep"),
        ("pretool_linter_config.json", "PY-LINTER-001", ""),
        ("pretool_ts_todo.json", "TS-QUALITY-003", "TODO"),
        ("pretool_test_loop_assert.json", "PY-TEST-003", ""),
        ("pretool_fixture_outside_conftest.json", "PY-TEST-004", "conftest"),
    ],
    ids=lambda p: p if isinstance(p, str) and p.endswith(".json") else "",
)
def test_fixture_denies(
    load_fixture: LoadFixture, fixture_name: str, rule_id: str, msg_fragment: str
) -> None:
    """Parametrised: each fixture must trigger its expected rule."""
    result = evaluate_payload(load_fixture(fixture_name))
    assert_denied_by(result, rule_id, msg_fragment)


# Tests where multiple rules may legitimately fire (order-dependent)
class TestMultiRuleDenyFixtures:
    def test_default_swallow(self, load_fixture: LoadFixture) -> None:
        """PY-EXC-001 or PY-QUALITY-005 may fire on log+return-default."""
        result = evaluate_payload(load_fixture("pretool_default_swallow.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "PY-QUALITY-005" in reason or "PY-EXC-001" in reason

    def test_fe_linter(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_fe_linter.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "FE-LINTER-001" in reason or "BUILTIN-PROTECTED-PATHS" in reason

    def test_design_tokens(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_design_tokens.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "STYLE-004" in reason or "STYLE-005" in reason

    def test_shell_bypass(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_shell_bypass.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "SHELL-001" in reason or "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in reason

    def test_quality_test_path(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_quality_test_path.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "QA-PATH-003" in reason or "BUILTIN-PROTECTED-PATHS" in reason


# ===========================================================================
# PreToolUse: inline payload deny tests
# ===========================================================================


class TestInlinePayloadDenies:
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param('git commit -n -m "skip"', id="n_before_message"),
            pytest.param("git commit -n", id="terminal_n"),
            pytest.param('git commit -m "skip" -n', id="terminal_n_after_message"),
            pytest.param('git commit -an -m "skip"', id="combined_short_flags"),
        ],
    )
    def test_git_n_shorthand(self, pretool_bash: BashBuilder, command: str) -> None:
        result = evaluate_payload(pretool_bash(command))
        assert_denied_by(result, "GIT-001")

    def test_protected_path_makefile(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("Makefile", "all:\n\techo hi\n"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")

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
        assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result)

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
        assert "BUILTIN-PROTECTED-PATHS" not in finding_ids(result)

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

    def test_broad_claude_protection_still_denies_protected_files_in_worktrees(
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
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")

    def test_protected_staging_rule_file_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        result = evaluate_payload(
            pretool_write(
                "src/vibeforcer/rules/python_ast/_staging/duplicate_rules.py",
                "from __future__ import annotations\n",
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS", "protected path")

    def test_system_path(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write("/etc/passwd", "x"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")

    def test_system_path_relative_escape(
        self, pretool_bash: BashBuilder, tmp_path: Path
    ) -> None:
        nested = tmp_path / "a" / "b" / "c" / "d"
        nested.mkdir(parents=True)
        result = evaluate_payload(
            pretool_bash("cat ../../../../../../../../etc/passwd", cwd=str(nested))
        )
        assert_denied_by(result, "GLOBAL-BUILTIN-SYSTEM-PROTECTION")

    def test_sensitive_data(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("cat ~/.ssh/id_rsa"))
        assert_denied_by(result, "GLOBAL-BUILTIN-SENSITIVE-DATA")

    def test_exec_protection_bash_write(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("echo x > .claude/hooks/run-pretool.sh"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")

    def test_exec_protection_bash_redirect_without_spaces(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("grep foo src/app.py>pyproject.toml"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")

    def test_exec_protection_bash_touch_makefile(
        self, pretool_bash: BashBuilder
    ) -> None:
        result = evaluate_payload(pretool_bash("touch Makefile"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")

    def test_exec_protection_write_config(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(pretool_write(".claude/hook-layer/config.json", "{}"))
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")

    def test_exec_protection_bash_write_staging_rule(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(
            pretool_bash(
                "echo '# temp' > src/vibeforcer/rules/python_ast/_staging/test_smell_rules.py"
            )
        )
        assert_denied_by(result, "BUILTIN-PROTECTED-PATHS")

    def test_security_bypass_permissions(self, pretool_write: WriteBuilder) -> None:
        result = evaluate_payload(
            pretool_write("src/settings.py", "BYPASS_PERMISSIONS = True\n")
        )
        assert_denied_by(result, "BUILTIN-RULEBOOK-SECURITY", "bypass")

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
        'src/sse_parsing.py and cloud agent_stream/sse.py; moved '
        'runtime_lifecycle.py."'
    )
    assert "src/sse_parsing.py" not in paths
    assert "agent_stream/sse.py" not in paths
    assert "runtime_lifecycle.py" not in paths


def test_shell_command_paths_still_captures_path_option_values() -> None:
    paths = shell_command_paths("tool --config=pyproject.toml --file src/app.py")
    assert "pyproject.toml" in paths
    assert "src/app.py" in paths


def test_powershell_git_no_verify_denied(tmp_path: Path) -> None:
    _ = (tmp_path / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
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
    _ = (tmp_path / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
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


def test_posttool_bash_reason_paths_do_not_trigger_ast_read_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": (
                'bd close job-hunter-6vc1 --reason="Centralized parsing in '
                'src/sse_parsing.py and cloud agent_stream/sse.py; moved '
                'runtime_lifecycle.py."'
            )
        },
        "cwd": str(repo),
        "session_id": "t",
    }
    result = evaluate_payload(payload)
    assert "PY-AST-001" not in finding_ids(result)


def test_morph_tool_is_edit_like() -> None:
    from vibeforcer.util.payloads import is_edit_like_tool

    assert is_edit_like_tool("morph")
    assert is_edit_like_tool("morph_edit_file")
    assert is_edit_like_tool("str_replace_editor")


# ===========================================================================
# PreToolUse: negative tests (must NOT deny)
# ===========================================================================


@pytest.mark.parametrize(
    "file_path, content, forbidden_rule",
    [
        pytest.param(
            "src/models/user.py",
            "from dataclasses import dataclass\n\n@dataclass\nclass User:\n    name: str\n    email: str\n",
            None,
            id="clean-python",
        ),
        pytest.param(
            "src/utils/format.ts",
            "export function formatDate(d: Date): string {\n  return d.toISOString();\n}\n",
            None,
            id="clean-typescript",
        ),
        pytest.param(
            "tests/conftest.py",
            "import pytest\n\n@pytest.fixture\ndef client():\n    return TestClient()\n",
            "PY-TEST-004",
            id="conftest-fixture-allowed",
        ),
        pytest.param(
            "src/hook_layer/config.py",
            "enabled_rules = {}\n",
            "BUILTIN-RULEBOOK-SECURITY",
            id="hook-source-not-blocked-by-security",
        ),
    ],
)
def test_write_not_denied(
    pretool_write: WriteBuilder,
    file_path: str,
    content: str,
    forbidden_rule: str | None,
) -> None:
    passed, detail = _assert_write_negative_case(
        pretool_write, file_path, content, forbidden_rule
    )
    assert passed, detail


@pytest.mark.parametrize(
    "command, forbidden_rule",
    [
        pytest.param("npm test", None, id="npm-test"),
        pytest.param("cat Makefile", None, id="cat-makefile"),
        pytest.param("cat .claude/hooks/run-pretool.sh", None, id="cat-hook-file"),
        pytest.param(
            "grep -n import src/hook_layer/engine.py",
            "PY-SHELL-001",
            id="grep-not-shell-edit",
        ),
    ],
)
def test_bash_not_denied(
    pretool_bash: BashBuilder,
    evaluate: EvaluateFn,
    command: str,
    forbidden_rule: str | None,
) -> None:
    passed, detail = _assert_bash_negative_case(
        pretool_bash, evaluate, command, forbidden_rule
    )
    assert passed, detail


def test_read_hook_file_allowed(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": ".claude/hooks/run-pretool.sh"},
    }
    result = evaluate_payload(payload)
    assert_not_denied(result)


def test_two_asserts_below_threshold(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(
        pretool_write(
            "tests/test_safe.py",
            "def test_ok():\n    assert x == 1\n    assert y == 2\n",
        )
    )
    assert "PY-TEST-001" not in finding_ids(result), "2 asserts below threshold"


# ===========================================================================
# Edge cases and boundary tests
# ===========================================================================


class TestEdgeCases:
    """Verify rules don't over-match on similar-looking but valid code."""

    @pytest.mark.parametrize(
        "code, should_deny",
        [
            pytest.param(
                "def safe_int(s):\n    try:\n        return int(s)\n    except ValueError:\n        pass\n",
                False,
                id="specific-exception-pass-allowed",
            ),
            pytest.param(
                "def get_item(d, k):\n    try:\n        return d[k]\n    except KeyError:\n        return None\n",
                False,
                id="specific-exception-return-none-allowed",
            ),
            pytest.param(
                (
                    "def process(items):\n"
                    "    for i in items:\n"
                    "        try:\n"
                    "            do(i)\n"
                    "        except Exception:\n"
                    "            continue\n"
                ),
                True,
                id="except-exception-continue-denied",
            ),
            pytest.param(
                (
                    "def fetch(url):\n"
                    "    try:\n"
                    "        return get(url).json()\n"
                    "    except Exception:\n"
                    "        return None\n"
                ),
                True,
                id="except-exception-return-none-denied",
            ),
            pytest.param(
                "def cleanup():\n    try:\n        os.remove(f)\n    except:\n        pass\n",
                True,
                id="bare-except-pass-denied",
            ),
        ],
    )
    def test_exc_002_boundaries(
        self, pretool_write: WriteBuilder, code: str, should_deny: bool
    ) -> None:
        result = evaluate_payload(pretool_write("src/module.py", code))
        ids = finding_ids(result)
        assert ("PY-EXC-002" in ids) is should_deny, (
            f"Unexpected PY-EXC-002 result for code:\n{code}"
        )

    def test_exc_002_single_line_default_return_denied(
        self, pretool_write: WriteBuilder
    ) -> None:
        code = "def f():\n    try:\n        return run()\n    except Exception: return []\n"
        result = evaluate_payload(pretool_write("src/module.py", code))
        assert "PY-EXC-002" in finding_ids(result)

    def test_any_builtin_not_denied(self, pretool_write: WriteBuilder) -> None:
        """Python's builtin any() must not trigger PY-TYPE-001."""
        result = evaluate_payload(
            pretool_write(
                "src/check.py",
                "def has_errors(items: list[str]) -> bool:\n"
                "    return any(item.startswith('ERROR') for item in items)\n",
            )
        )
        assert "PY-TYPE-001" not in finding_ids(result)

    def test_normal_git_commit_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("git commit -m 'fix: thing'"))
        assert "GIT-001" not in finding_ids(result)

    def test_safe_redirect_allowed(self, pretool_bash: BashBuilder) -> None:
        result = evaluate_payload(pretool_bash("echo hello > output.txt"))
        assert "SHELL-001" not in finding_ids(result)

    def test_asserts_with_messages_allowed(self, pretool_write: WriteBuilder) -> None:
        code = (
            "def test_validated():\n"
            "    assert x == 1, 'expected 1'\n"
            "    assert y == 2, 'expected 2'\n"
            "    assert z == 3, 'expected 3'\n"
            "    assert w == 4, 'expected 4'\n"
        )
        result = evaluate_payload(pretool_write("tests/test_good.py", code))
        assert "PY-TEST-001" not in finding_ids(result)

    @pytest.mark.parametrize(
        "file_path, content",
        [
            pytest.param(
                "docs/README.md",
                "# Exceptions\n\nexcept Exception:\n    pass\n\nfrom typing import Any\n",
                id="markdown",
            ),
            pytest.param(
                "config.json",
                '{\n  "type": "Any"\n}\n',
                id="json",
            ),
        ],
    )
    def test_non_python_not_denied_by_python_rules(
        self, pretool_write: WriteBuilder, file_path: str, content: str
    ) -> None:
        result = evaluate_payload(pretool_write(file_path, content))
        py_rules = {r for r in finding_ids(result) if r.startswith("PY-")}
        assert not py_rules, f"Non-Python file should not trigger: {py_rules}"


# ===========================================================================
# BASELINE-001: increase vs decrease
# ===========================================================================


class TestBaselineGuard:
    def _write_baseline(self, tmp_path: Path, rules: dict[str, list[str]]) -> Path:
        _ = (tmp_path / "quality_gate.toml").write_text(
            "[quality_gate]\nenabled = true\n", encoding="utf-8"
        )
        p = tmp_path / "baselines.json"
        _ = p.write_text(
            json.dumps(
                {"generated_at": "2026-01-01", "rules": rules, "schema_version": 1}
            )
        )
        return p

    def test_increase_blocked(self, tmp_path: Path) -> None:
        existing = self._write_baseline(tmp_path, {"high-complexity": ["h1", "h2"]})
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1", "h2", "h3", "h4"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(existing), "content": new_content},
            }
        )
        result = evaluate_payload(payload)
        assert_denied_by(result, "BASELINE-001", "increasing the baseline")

    @pytest.mark.parametrize(
        "command",
        [
            "quality-gate baseline .",
            "vibeforcer lint baseline .",
            "vfc lint baseline .",
        ],
    )
    def test_repo_wide_baseline_commands_blocked(self, command: str) -> None:
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(BUNDLE_ROOT),
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        )
        result = evaluate_payload(payload)
        assert_denied_by(result, "BASELINE-001", "technical debt")

    def test_decrease_allowed(self, tmp_path: Path) -> None:
        existing = self._write_baseline(
            tmp_path, {"high-complexity": ["h1", "h2", "h3"]}
        )
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(existing), "content": new_content},
            }
        )
        result = evaluate_payload(payload)
        assert_not_denied(result)


# ===========================================================================
# PermissionRequest event
# ===========================================================================


def test_permission_request_denies_makefile(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PermissionRequest",
        "tool_name": "Write",
        "tool_input": {"file_path": "Makefile", "content": "all:\n\techo hi\n"},
    }
    result = evaluate_payload(payload)
    inner = nested_output(hook_output(result), "decision")
    assert inner["behavior"] == "deny"
    assert "BUILTIN-PROTECTED-PATHS" in output_string(inner, "message")


# ===========================================================================
# UserPromptSubmit
# ===========================================================================


def test_prompt_injects_context(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "refactor the auth module",
    }
    result = evaluate_payload(payload)
    spec = hook_output(result)
    assert spec["hookEventName"] == "UserPromptSubmit"
    ctx = required_string(spec, "additionalContext")
    assert "Organization prompt context" in ctx
    assert "Repository Rules" in ctx


# ===========================================================================
# PostToolUse (AST rules)
# ===========================================================================


def test_long_param_list_blocks(tmp_project: Path) -> None:
    target = tmp_project / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def build(a, b, c, d, e):\n    return a + b + c + d + e\n")
    payload = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/sample.py", "content": target.read_text()},
        "tool_response": {"filePath": "src/sample.py", "success": True},
    }
    result = evaluate_payload(payload)
    assert_blocked(result)
    reason = required_string(require_output(result), "reason")
    assert "PY-CODE-009" in reason
    assert "parameters" in reason.lower()


# ===========================================================================
# Stop / SubagentStop
# ===========================================================================


def test_stop_preexisting_blocked(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("stop_preexisting.json"))
    assert_blocked(result, "STOP-001")


def test_subagent_stop_preexisting_blocked(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "SubagentStop",
        "stop_response": "The type error was already existed before my changes.",
    }
    result = evaluate_payload(payload)
    assert_blocked(result, "STOP-001")


def test_clean_stop_gets_quality_reminder(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "Stop",
        "stop_response": "All tasks completed successfully.",
    }
    result = evaluate_payload(payload)
    output = require_output(result)
    assert output_string(output, "decision") != "block"
    ctx = output_string(output, "systemMessage") or output_string(
        hook_output(result), "additionalContext"
    )
    assert "quality" in ctx.lower(), f"Expected quality reminder, got: {ctx}"


def test_git_commit_gets_quality_context(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'fix: something'"},
    }
    result = evaluate_payload(payload)
    output = require_output(result)
    ctx = output_string(output, "systemMessage") or output_string(
        hook_output(result), "additionalContext"
    )
    assert "quality" in ctx.lower()
    assert "GIT-002" in finding_ids(result)


# ===========================================================================
# SessionStart
# ===========================================================================


def _init_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    worktree = tmp_path / "repo-worktree"
    repo.mkdir()
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n", encoding="utf-8"
    )
    _ = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = (repo / "README.md").write_text("root\n", encoding="utf-8")
    _ = subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "worktree", "add", "-b", "feature/worktree-support", str(worktree)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo, worktree
def _fake_non_default_vibeforcer_git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    if args[-3:] == ["remote", "get-url", "origin"]:
        return "https://lab.baked.rocks/claude/vibeforcer.git"
    if args[-2:] == ["branch", "--show-current"]:
        return "feature/worktree-support"
    if args[-2:] == ["symbolic-ref", "refs/remotes/origin/HEAD"]:
        return "refs/remotes/origin/feature/worktree-support"
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout.strip() or None
VALID_TOP_LEVEL_KEYS = {
    "decision",
    "reason",
    "hookSpecificOutput",
    "continue",
    "stopReason",
    "suppressOutput",
    "systemMessage",
}
EVENTS_NO_HOOK_SPECIFIC = (
    "Stop",
    "SubagentStop",
    "ConfigChange",
    "PostToolUseFailure",
    "TaskCompleted",
    "TeammateIdle",
)
def _pretool_write_payload(cwd: Path, file_path: str, content: str = "x") -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }
def _pretool_bash_payload(cwd: Path, command: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
def _evaluate_pretool_write(cwd: Path, file_path: str, content: str = "x") -> EngineResult:
    return evaluate_payload(_pretool_write_payload(cwd, file_path, content))
def _evaluate_pretool_bash(cwd: Path, command: str) -> EngineResult:
    return evaluate_payload(_pretool_bash_payload(cwd, command))
def _fake_vibeforcer_worktree_git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    if args[-3:] == ["remote", "get-url", "origin"]:
        return "https://lab.baked.rocks/claude/vibeforcer.git"
    if args[-2:] == ["branch", "--show-current"]:
        return "feature/worktree-support"
    if args[-2:] == ["symbolic-ref", "refs/remotes/origin/HEAD"]:
        return "refs/remotes/origin/feature/worktree-support"
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout.strip() or None
def _pretool_delete_payload(cwd: Path, file_path: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Delete",
        "tool_input": {"file_path": file_path},
    }
# Exported test support used by split test modules.
__all__ = ('Any', 'BUNDLE_ROOT', 'BashBuilder', 'Callable', 'EVENTS_NO_HOOK_SPECIFIC', 'EngineResult', 'EvaluateFn', 'FIXTURE_FILE_NAMES', 'LoadFixture', 'MonkeyPatch', 'ObjectDict', 'Path', 'VALID_TOP_LEVEL_KEYS', 'VIRTUALENV_PARSE_SKIP_PATHS', 'WriteBuilder', '_assert_bash_negative_case', '_assert_worktree_marker_copied', '_assert_write_negative_case', '_disable_default_post_edit_quality', '_disabled_rule_findings', '_enable_failing_post_edit_quality_command', '_evaluate_post_edit_bash', '_evaluate_pretool_bash', '_evaluate_pretool_write', '_fake_non_default_vibeforcer_git_output', '_fake_vibeforcer_worktree_git_output', '_fixture_output', '_init_git_worktree', '_is_not_denied', '_keep_default_config', '_latest_trace_event', '_post_edit_bash_payload', '_pretool_bash_payload', '_pretool_delete_payload', '_pretool_write_payload', '_repo_with_moved_parse_error', '_rule_build_context', '_set_skip_paths', '_strict_rule_id_sets', '_write_config_from_defaults', '_write_quality_gate', '_write_skip_paths_config', 'assert_blocked', 'assert_denied_by', 'assert_not_denied', 'cast', 'evaluate_payload', 'finding_ids', 'hook_output', 'json', 'nested_output', 'object_dict', 'output_string', 'pytest', 're', 'require_output', 'required_string', 'shell_command_paths', 'subprocess')
