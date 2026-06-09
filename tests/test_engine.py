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
from slopgate._types import ObjectDict, object_dict
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from slopgate.util.payloads import shell_command_paths
from tests.support import (
    BUNDLE_ROOT,
    LoadFixture,
    WriteBuilder,
    BashBuilder,
    EvaluateFn,
    assert_blocked,
    assert_denied_by,
    assert_not_denied,
    assert_asked_by,
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
    from slopgate.config import load_config
    from slopgate.context import HookContext
    from slopgate.rules import build_rules
    from slopgate.state import HookStateStore
    from slopgate.trace import TraceWriter
    from slopgate.util.payloads import HookPayload
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
    from slopgate.config import load_config
    from slopgate.context import HookContext
    import slopgate.rules as rules_mod
    from slopgate.state import HookStateStore
    from slopgate.trace import TraceWriter
    from slopgate.util.payloads import HookPayload
    config = load_config()
    trace = TraceWriter(config.trace_dir)
    state = HookStateStore(config.trace_dir)
    payload = HookPayload(load_fixture("pretool_git_no_verify.json"), config)
    ctx = HookContext(payload=payload, config=config, trace=trace, state=state)
    return rules_mod, ctx
def _write_slopgate(
    repo: Path, content: str = "[slopgate]\nenabled = true\n"
) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / "slopgate.toml").write_text(content, encoding="utf-8")
    return repo
def _assert_worktree_marker_copied(repo: Path, worktree_marker: Path) -> None:
    assert worktree_marker.exists()
    assert worktree_marker.read_text(encoding="utf-8") == (repo / "slopgate.toml").read_text(
        encoding="utf-8"
    )
def _write_config_from_defaults(
    tmp_path: Path, monkeypatch: MonkeyPatch, mutate: Callable[[dict[str, Any]], None]
) -> Path:
    defaults_path = BUNDLE_ROOT / "src" / "slopgate" / "resources" / "defaults.json"
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    mutate(defaults)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(defaults), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(cfg))
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
    from slopgate.adapters import get_adapter
    from slopgate.context import build_context
    from slopgate.rules import build_always_on_rules, build_repo_strict_rules
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
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
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
def _init_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    worktree = tmp_path / "repo-worktree"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
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
def _fake_non_default_slopgate_git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    if args[-3:] == ["remote", "get-url", "origin"]:
        return "https://lab.baked.rocks/claude/slopgate.git"
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
def _fake_slopgate_worktree_git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    if args[-3:] == ["remote", "get-url", "origin"]:
        return "https://lab.baked.rocks/claude/slopgate.git"
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
__all__ = ('Any', 'BUNDLE_ROOT', 'BashBuilder', 'Callable', 'EVENTS_NO_HOOK_SPECIFIC', 'EngineResult', 'EvaluateFn', 'FIXTURE_FILE_NAMES', 'LoadFixture', 'MonkeyPatch', 'ObjectDict', 'Path', 'VALID_TOP_LEVEL_KEYS', 'VIRTUALENV_PARSE_SKIP_PATHS', 'WriteBuilder', '_assert_bash_negative_case', '_assert_worktree_marker_copied', '_assert_write_negative_case', '_disable_default_post_edit_quality', '_disabled_rule_findings', '_enable_failing_post_edit_quality_command', '_evaluate_post_edit_bash', '_evaluate_pretool_bash', '_evaluate_pretool_write', '_fake_non_default_slopgate_git_output', '_fake_slopgate_worktree_git_output', '_fixture_output', '_init_git_worktree', '_is_not_denied', '_keep_default_config', '_latest_trace_event', '_post_edit_bash_payload', '_pretool_bash_payload', '_pretool_delete_payload', '_pretool_write_payload', '_repo_with_moved_parse_error', '_rule_build_context', '_set_skip_paths', '_strict_rule_id_sets', '_write_config_from_defaults', '_write_slopgate', '_write_skip_paths_config', 'assert_blocked', 'assert_denied_by', 'assert_not_denied', 'assert_asked_by', 'cast', 'evaluate_payload', 'finding_ids', 'hook_output', 'json', 'nested_output', 'object_dict', 'output_string', 'pytest', 're', 'require_output', 'required_string', 'shell_command_paths', 'subprocess')
