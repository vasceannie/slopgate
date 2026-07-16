from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import cast
import pytest
from slopgate.config._discovery import detect_root, resolve_config_path
from slopgate.config._repo import (
    ensure_worktree_enrollment,
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    list_git_worktrees,
    resolve_main_git_repo_root,
    resolve_repo_root,
)
from slopgate.installer._safe_files import (
    backup_existing_file,
    backup_existing_file_and_report,
)
from slopgate.installer._shared import (
    base_invocation,
    coerce_hook_entries,
    find_binary,
    merge_owned_hooks_into,
    require_json_object,
    write_json_with_backup,
)
from slopgate.rules.common._shell_read import (
    FullFileReadRule,
    PromptContextRule,
    ProtectedPathsRule,
)
from slopgate.context import HookContext
from slopgate.rules.python_ast._helpers import (
    decision_for_context,
    detect_family_prefix,
    evaluate_common,
)
from slopgate.search.cli import (
    cmd_add,
    cmd_list,
    cmd_models,
    cmd_reindex,
    cmd_remove,
    cmd_search,
    cmd_sync,
    cmd_use,
)
from slopgate.search.config import SearchConfig, detect_provider, expand, save_config
import slopgate.search.config
from slopgate.adapters.cursor import CursorAdapter
from slopgate.models import RuleFinding, Severity


def _repo_helper_snapshot(repo_path: Path) -> dict[str, object]:
    return {
        "main_root": resolve_main_git_repo_root(repo_path),
        "repo_root": resolve_repo_root(repo_path),
        "worktrees": list_git_worktrees(repo_path),
        "enrolled": is_repo_enrolled(repo_path),
        "disabled": is_repo_disabled(repo_path),
        "worktree_enrollment": ensure_worktree_enrollment(repo_path),
        "skipped": is_path_skipped(
            repo_path / "src", [f"*/{(repo_path / 'src').name}"]
        ),
    }


def _installer_shared_snapshot(existing: Path, missing: Path) -> dict[str, object]:
    config: dict[str, object] = {"hooks": {}}
    merge_owned_hooks_into(config, {"PreToolUse": []})
    backup_path = backup_existing_file(existing)
    backup_existing_file_and_report(existing, "hooks")
    write_json_with_backup(missing, {"ok": True}, "hooks")
    return {
        "binary": find_binary(),
        "invocation": base_invocation(find_binary()),
        "hooks": coerce_hook_entries([]),
        "json": require_json_object(existing, "hooks", action="install"),
        "backup_path": backup_path,
        "missing_payload": json.loads(missing.read_text(encoding="utf-8")),
        "merged_hooks": config["hooks"],
    }


def test_repo_helpers_handle_non_git_directories(tmp_path: Path) -> None:
    src_path = tmp_path / "src"
    skip_pattern = f"*/{src_path.name}"
    assert _repo_helper_snapshot(tmp_path) == {
        "main_root": None,
        "repo_root": None,
        "worktrees": [],
        "enrolled": False,
        "disabled": False,
        "worktree_enrollment": None,
        "skipped": is_path_skipped(src_path, [skip_pattern]),
    }


def test_config_discovery_helpers_use_temp_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_file))
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path))
    assert {"config_path": resolve_config_path(), "root": detect_root()} == {
        "config_path": config_file.resolve(),
        "root": tmp_path.resolve(),
    }


def test_python_ast_helpers_expose_public_entrypoints() -> None:
    class DummyContext:
        event_name = "PreToolUse"

    assert {
        "decision": decision_for_context(cast(HookContext, DummyContext())),
        "family": detect_family_prefix(["parse_a", "parse_b", "parse_c"]),
        "common": evaluate_common.__name__,
    } == {"decision": "deny", "family": "parse_", "common": "evaluate_common"}


def test_search_cli_command_callables_are_registered() -> None:
    commands = (
        cmd_models,
        cmd_use,
        cmd_list,
        cmd_add,
        cmd_search,
        cmd_remove,
        cmd_sync,
        cmd_reindex,
    )
    assert all((callable(command) for command in commands))


def test_search_config_helpers_expand_save_and_detect_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "isx" / "config.json"
    monkeypatch.setattr(slopgate.search.config, "APP_CONFIG", config_path)
    monkeypatch.setattr(slopgate.search.config, "APP_DIR", config_path.parent)
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    target = tmp_path / "nested" / "islands.yml"
    assert expand(None, default=target) == target
    assert detect_provider() in {"litellm", "ollama"}
    save_config(SearchConfig(islands_config=str(target)))
    assert json.loads(config_path.read_text(encoding="utf-8"))["islands_config"] == str(
        target
    )


def test_installer_shared_helpers_handle_missing_and_backup_paths(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    existing = tmp_path / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    snapshot = _installer_shared_snapshot(existing, missing)
    assert {
        "hooks": snapshot["hooks"],
        "json": snapshot["json"],
        "missing_payload": snapshot["missing_payload"],
        "merged_hooks": snapshot["merged_hooks"],
        "binary_is_str": isinstance(snapshot["binary"], str),
        "backup_created": snapshot["backup_path"] is not None,
    } == {
        "hooks": [],
        "json": {},
        "missing_payload": {"ok": True},
        "merged_hooks": {"PreToolUse": []},
        "binary_is_str": True,
        "backup_created": True,
    }


def test_shell_read_rules_expose_public_rule_ids() -> None:
    assert {
        "prompt": PromptContextRule().rule_id,
        "full_file": FullFileReadRule().rule_id,
        "protected": ProtectedPathsRule().rule_id,
    } == {
        "prompt": "BUILTIN-INJECT-PROMPT",
        "full_file": "BUILTIN-ENFORCE-FULL-READ",
        "protected": "BUILTIN-PROTECTED-PATHS",
    }


def test_cursor_adapter_exposes_public_render_and_normalize() -> None:
    adapter = CursorAdapter()
    finding = RuleFinding(
        rule_id="COVERAGE-001",
        title="coverage",
        severity=Severity.MEDIUM,
        decision="deny",
        message="coverage probe",
    )
    normalized = adapter.normalize_payload(
        {"hook_event_name": "preToolUse", "cwd": "/tmp"}
    )
    output = adapter.render_output("PreToolUse", [finding], decision="deny")
    assert {
        "name": adapter.name,
        "event": normalized["hook_event_name"],
        "permission": output["permission"] if output else None,
    } == {"name": "cursor", "event": "PreToolUse", "permission": "deny"}


def test_search_cli_init_returns_zero_for_dry_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from slopgate.search.cli import cmd_init

    app_dir = tmp_path / ".config" / "slopgate"
    app_dir.mkdir(parents=True)
    config_path = app_dir / "config.json"
    islands_path = tmp_path / "islands.toml"
    monkeypatch.setattr(slopgate.search.config, "APP_CONFIG", config_path)
    monkeypatch.setattr(slopgate.search.config, "APP_DIR", app_dir)
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(
        force=True,
        integration="none",
        islands_config=str(islands_path),
        provider="ollama",
        base_url="http://127.0.0.1:11434",
        model="test-model",
        binary="islands-ollama",
        api_key_env="",
        api_key_value="",
        skill_name="",
        skill_target="",
        opencode_plugin_path="",
        opencode_config="",
    )
    assert cmd_init(args) == 0
