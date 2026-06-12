"""Shared non-fixture helpers for engine hook tests."""

from __future__ import annotations

__all__ = [
    "Callable",
    "Path",
    "MonkeyPatch",
    "ObjectDict",
    "object_dict",
    "HookContext",
    "evaluate_payload",
    "EngineResult",
    "BUNDLE_ROOT",
    "BashBuilder",
    "EvaluateFn",
    "LoadFixture",
    "WriteBuilder",
    "finding_ids",
    "output_string",
    "VIRTUALENV_PARSE_SKIP_PATHS",
    "disabled_rule_findings",
    "rule_build_context",
    "write_slopgate",
    "assert_worktree_marker_copied",
    "write_config_from_defaults",
    "enable_failing_post_edit_quality_command",
    "disable_default_post_edit_quality",
    "keep_default_config",
    "latest_trace_event",
    "_set_skip_paths",
    "write_skip_paths_config",
    "post_edit_bash_payload",
    "evaluate_post_edit_bash",
    "strict_rule_id_sets",
    "repo_with_moved_parse_error",
    "_is_not_denied",
    "assert_write_negative_case",
    "assert_bash_negative_case",
    "init_git_worktree",
    "fake_slopgate_worktree_git_output",
    "_fake_non_default_slopgate_git_output",
    "pretool_write_payload",
    "pretool_bash_payload",
    "evaluate_pretool_write",
    "evaluate_pretool_bash",
]


import json
import types
from collections.abc import Callable
from pathlib import Path

from pytest import MonkeyPatch
from slopgate._types import ObjectDict, object_dict
from slopgate.context import HookContext
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from tests.engine.git_worktree_support import (
    _fake_non_default_slopgate_git_output,
    fake_slopgate_worktree_git_output,
    init_git_worktree,
)
from tests.support import (
    BUNDLE_ROOT,
    BashBuilder,
    EvaluateFn,
    LoadFixture,
    WriteBuilder,
    finding_ids,
    output_string,
)

VIRTUALENV_PARSE_SKIP_PATHS = (
    ".venv/lib/python3.12/site-packages/pkg/bad.py",
    "venv/lib/python3.12/site-packages/pkg/bad.py",
    "env/lib/python3.12/site-packages/pkg/bad.py",
    "src/pkg/site-packages/vendor/bad.py",
)


def disabled_rule_findings(
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


def rule_build_context(
    load_fixture: LoadFixture,
) -> tuple[types.ModuleType, HookContext]:
    from slopgate.config import load_config
    from slopgate.context import HookContext
    import slopgate.rules
    from slopgate.state import HookStateStore
    from slopgate.trace import TraceWriter
    from slopgate.util.payloads import HookPayload

    config = load_config()
    trace = TraceWriter(config.trace_dir)
    state = HookStateStore(config.trace_dir)
    payload = HookPayload(load_fixture("pretool_git_no_verify.json"), config)
    ctx = HookContext(payload=payload, config=config, trace=trace, state=state)
    return (slopgate.rules, ctx)


def write_slopgate(repo: Path, content: str = "[slopgate]\nenabled = true\n") -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / "slopgate.toml").write_text(content, encoding="utf-8")
    return repo


def assert_worktree_marker_copied(repo: Path, worktree_marker: Path) -> None:
    assert worktree_marker.exists()
    assert worktree_marker.read_text(encoding="utf-8") == (
        repo / "slopgate.toml"
    ).read_text(encoding="utf-8")


def write_config_from_defaults(
    tmp_path: Path, monkeypatch: MonkeyPatch, mutate: Callable[[ObjectDict], None]
) -> Path:
    defaults_path = BUNDLE_ROOT / "src" / "slopgate" / "resources" / "defaults.json"
    defaults = object_dict(json.loads(defaults_path.read_text(encoding="utf-8")))
    mutate(defaults)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(defaults), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(cfg))
    return cfg


def enable_failing_post_edit_quality_command(defaults: ObjectDict) -> None:
    quality = object_dict(defaults.get("post_edit_quality"))
    quality["enabled"] = True
    quality["block_on_failure"] = True
    quality["commands_by_language"] = {"python": ["pwd && false"]}
    defaults["post_edit_quality"] = quality


def disable_default_post_edit_quality(defaults: ObjectDict) -> None:
    quality = object_dict(defaults.get("post_edit_quality"))
    quality["enabled"] = False
    defaults["post_edit_quality"] = quality


def keep_default_config(defaults: ObjectDict) -> None:
    _ = defaults


def latest_trace_event(tmp_path: Path) -> ObjectDict:
    events = (
        (tmp_path / "vf-root" / "logs" / "events.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert events
    return object_dict(json.loads(events[-1]))


def _set_skip_paths(defaults: ObjectDict, repo: Path) -> None:
    defaults["skip_paths"] = [str(repo.resolve())]


def write_skip_paths_config(
    tmp_path: Path, monkeypatch: MonkeyPatch, repo: Path
) -> Path:
    def mutate(defaults: ObjectDict) -> None:
        _set_skip_paths(defaults, repo)

    return write_config_from_defaults(tmp_path, monkeypatch, mutate)


def post_edit_bash_payload(
    cwd: Path, command: str = "echo 'print(1)' > app.py"
) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def evaluate_post_edit_bash(
    cwd: Path, command: str = "echo 'print(1)' > app.py"
) -> EngineResult:
    return evaluate_payload(post_edit_bash_payload(cwd, command))


def strict_rule_id_sets(repo: Path) -> tuple[set[str], set[str]]:
    from slopgate.adapters import get_adapter
    from slopgate.context import build_context
    from slopgate.rules import build_always_on_rules, build_repo_strict_rules

    ctx = build_context(
        get_adapter("claude").normalize_payload(
            pretool_write_payload(repo, "src/app.py", "from typing import Any\n")
        )
    )
    return (
        {rule.rule_id for rule in build_always_on_rules(ctx)},
        {rule.rule_id for rule in build_repo_strict_rules(ctx)},
    )


def repo_with_moved_parse_error(tmp_path: Path) -> Path:
    repo = tmp_path / "repo_move_ast_health"
    source_dir = repo / "src" / "pkg"
    target_dir = source_dir / "moved"
    target_dir.mkdir(parents=True)
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
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


def assert_write_negative_case(
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
    detail = f"Unexpected deny state for {file_path}: forbidden_rule={forbidden_rule!r}, ids={ids}, output={result.output!r}"
    return (passes_expectation, detail)


def assert_bash_negative_case(
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
    detail = f"Unexpected deny state for command {command!r}: forbidden_rule={forbidden_rule!r}, ids={ids}, output={result.output!r}"
    return (passes_expectation, detail)


def pretool_write_payload(cwd: Path, file_path: str, content: str = "x") -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def pretool_bash_payload(cwd: Path, command: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def evaluate_pretool_write(
    cwd: Path, file_path: str, content: str = "x"
) -> EngineResult:
    return evaluate_payload(pretool_write_payload(cwd, file_path, content))


def evaluate_pretool_bash(cwd: Path, command: str) -> EngineResult:
    return evaluate_payload(pretool_bash_payload(cwd, command))
