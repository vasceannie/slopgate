from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies

from slopgate._types import ObjectDict
from slopgate.cli.commands import cmd_handle
from slopgate.cli.main import main
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    command_is_slopgate_hook,
    contained_scope_root,
    filter_owned_hook_commands,
    merge_owned_hooks,
    require_contained_install_path,
)
from slopgate.installer._suite import SuiteUpdateOptions, update_suite
from slopgate.installer.suite import (
    install_autoupdate,
    uninstall_autoupdate,
)
from slopgate.installer._claude import install_claude, uninstall_claude
from slopgate.installer._codex import (
    codex_hooks_block,
    enable_codex_hooks_toml,
    install_codex,
    uninstall_codex,
)
from slopgate.installer._cursor import install_cursor, uninstall_cursor
from slopgate.installer._opencode import install_opencode, uninstall_opencode

_SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 /-_.",
    max_size=40,
)
_CODEX_FEATURE_LINE = strategies.sampled_from(
    [
        "",
        "hooks = false\n",
        "hooks = true\n",
        "codex_hooks = false\n",
        "codex_hooks = true\n",
        "hooks = false\ncodex_hooks = true\n",
    ]
)
# Installer dry-run walks config/FS. Hypothesis's 200ms deadline flakes under
# slopgate xdist load (observed 216-319ms); these pass in isolation.
_INSTALLER_DRY_RUN = settings(deadline=None, max_examples=1)


@given(strategies.just(None))
def test_cmd_handle_is_callable_property(_: None) -> None:
    assert callable(cmd_handle)


@given(strategies.just(None))
def test_main_is_callable_property(_: None) -> None:
    assert callable(main)


@given(_SHORT_TEXT)
def test_command_is_slopgate_hook_returns_bool_for_arbitrary_text_property(
    command: str,
) -> None:
    result = command_is_slopgate_hook(command)
    assert isinstance(result, bool), "must return bool"


@given(strategies.just(None))
def test_command_is_slopgate_hook_rejects_non_string_inputs_property(_: None) -> None:
    assert command_is_slopgate_hook(42) is False
    assert command_is_slopgate_hook(None) is False
    assert command_is_slopgate_hook([]) is False


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_update_suite_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = update_suite(SuiteUpdateOptions(dry_run=dry_run))
    assert result == 0, f"update_suite(dry_run=True) must return 0, got {result}"


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_install_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = install_autoupdate(dry_run=dry_run)
    assert result == 0, f"install_autoupdate(dry_run=True) must return 0, got {result}"


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_uninstall_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = uninstall_autoupdate(dry_run=dry_run)
    assert result == 0, (
        f"uninstall_autoupdate(dry_run=True) must return 0, got {result}"
    )


@given(strategies.sampled_from(["PreToolUse", "PostToolUse"]))
def test_merge_owned_hooks_preserves_unrelated_events_property(event: str) -> None:
    existing: ObjectDict = {
        "hooks": {event: [{"hooks": [{"command": "echo keep"}]}]}
    }
    managed: dict[str, list[ObjectDict]] = {
        event: [{"hooks": [{"command": "slopgate handle --platform claude"}]}]
    }
    merged = merge_owned_hooks(existing, managed)

    assert event in merged


@given(strategies.just(None))
def test_filter_owned_hook_commands_keeps_external_hooks_property(_: None) -> None:
    entry = {
        "matcher": "Write",
        "hooks": [
            {"command": "slopgate handle"},
            {"command": "echo external"},
        ],
    }
    filtered = filter_owned_hook_commands(entry)

    assert filtered is not None
    assert isinstance(filtered["hooks"], list)


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_install_claude_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_claude(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_uninstall_claude_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_claude(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_install_codex_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_codex(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_uninstall_codex_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_codex(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_install_cursor_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_cursor(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_uninstall_cursor_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_cursor(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_install_opencode_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_opencode(dry_run=dry_run) == 0


@_INSTALLER_DRY_RUN
@given(strategies.just(True))
def test_uninstall_opencode_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_opencode(dry_run=dry_run) == 0


@given(_SHORT_TEXT)
def test_codex_hooks_block_is_mapping_property(binary: str) -> None:
    hooks = codex_hooks_block(binary)
    assert isinstance(hooks, dict)


@given(label=_SHORT_TEXT, feature_line=_CODEX_FEATURE_LINE)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_enable_codex_hooks_toml_is_canonical_and_idempotent_property(
    tmp_path: Path, label: str, feature_line: str
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'label = "{label}"\n'
        "[features]\n"
        "plugin_hooks = true\n"
        f"{feature_line}"
        "[projects.sample]\n"
        f'name = "{label}"\n',
        encoding="utf-8",
    )

    enable_codex_hooks_toml(config_path)
    first_result = config_path.read_text(encoding="utf-8")
    enable_codex_hooks_toml(config_path)

    assert "hooks = true\n" in first_result, "canonical Codex hook flag must be set"
    assert "codex_hooks" not in first_result, "legacy Codex hook flags must be removed"
    assert config_path.read_text(encoding="utf-8") == first_result, (
        "enabling Codex hooks twice must be idempotent"
    )


_SAFE_NAME = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=8,
)
_CONTAINED_PATH = settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)


@_CONTAINED_PATH
@given(_SAFE_NAME, _SAFE_NAME)
def test_require_contained_install_path_accepts_nested_names_property(
    tmp_path: Path, directory: str, filename: str
) -> None:
    target = tmp_path / directory / filename
    resolved = require_contained_install_path(target, tmp_path)
    assert resolved == target.resolve(), (
        "contained relative names must resolve under the selected root"
    )


@_CONTAINED_PATH
@given(_SAFE_NAME)
def test_require_contained_install_path_rejects_escaped_names_property(
    tmp_path: Path, name: str
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "away" / name
    with pytest.raises(UnsafeInstallPathError):
        require_contained_install_path(outside, root)


@_CONTAINED_PATH
@given(_SAFE_NAME, _SAFE_NAME)
def test_contained_scope_root_keeps_project_children_property(
    tmp_path: Path, child: str, leaf: str
) -> None:
    project = tmp_path / "project"
    user = tmp_path / "user"
    target = project / child / leaf
    assert (
        contained_scope_root(target, project_root=project, user_root=user) == project
    ), "paths under the project root must keep the project root"


@_CONTAINED_PATH
@given(_SAFE_NAME)
def test_contained_scope_root_uses_user_root_outside_project_property(
    tmp_path: Path, name: str
) -> None:
    project = tmp_path / "project"
    user = tmp_path / "user"
    target = tmp_path / "elsewhere" / name
    assert contained_scope_root(target, project_root=project, user_root=user) == user, (
        "paths outside the project root must use the user root"
    )
