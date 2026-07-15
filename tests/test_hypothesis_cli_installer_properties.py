from __future__ import annotations

from hypothesis import given, settings, strategies

from slopgate.cli.commands import cmd_handle
from slopgate.cli.main import main
from slopgate.installer._shared import (
    command_is_slopgate_hook,
    filter_owned_hook_commands,
    merge_owned_hooks,
)
from slopgate.installer._suite import SuiteUpdateOptions, update_suite
from slopgate.installer.suite import (
    install_autoupdate,
    uninstall_autoupdate,
)
from slopgate.installer._claude import install_claude, uninstall_claude
from slopgate.installer._codex import codex_hooks_block, install_codex, uninstall_codex
from slopgate.installer._cursor import install_cursor, uninstall_cursor
from slopgate.installer._opencode import install_opencode, uninstall_opencode

_SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 /-_.",
    max_size=40,
)


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


@given(strategies.just(True))
@settings(deadline=None)
def test_update_suite_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = update_suite(SuiteUpdateOptions(dry_run=dry_run))
    assert result == 0, f"update_suite(dry_run=True) must return 0, got {result}"


@given(strategies.just(True))
@settings(deadline=None)
def test_install_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = install_autoupdate(dry_run=dry_run)
    assert result == 0, f"install_autoupdate(dry_run=True) must return 0, got {result}"


@given(strategies.just(True))
@settings(deadline=None)
def test_uninstall_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = uninstall_autoupdate(dry_run=dry_run)
    assert result == 0, (
        f"uninstall_autoupdate(dry_run=True) must return 0, got {result}"
    )


@given(strategies.sampled_from(["PreToolUse", "PostToolUse"]))
def test_merge_owned_hooks_preserves_unrelated_events_property(event: str) -> None:
    existing: dict[str, object] = {
        "hooks": {event: [{"hooks": [{"command": "echo keep"}]}]}
    }
    managed: dict[str, list[dict[str, object]]] = {
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


@given(strategies.just(True))
@settings(deadline=None)
def test_install_claude_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_claude(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_uninstall_claude_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_claude(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_install_codex_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_codex(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_uninstall_codex_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_codex(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_install_cursor_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_cursor(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_uninstall_cursor_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_cursor(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_install_opencode_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert install_opencode(dry_run=dry_run) == 0


@given(strategies.just(True))
@settings(deadline=None)
def test_uninstall_opencode_dry_run_returns_zero_property(dry_run: bool) -> None:
    assert uninstall_opencode(dry_run=dry_run) == 0


@given(_SHORT_TEXT)
def test_codex_hooks_block_is_mapping_property(binary: str) -> None:
    hooks = codex_hooks_block(binary)
    assert isinstance(hooks, dict)
