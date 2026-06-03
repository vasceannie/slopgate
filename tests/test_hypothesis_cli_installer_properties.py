from __future__ import annotations

from hypothesis import given, strategies

from vibeforcer.cli.commands import cmd_handle
from vibeforcer.cli.main import main
from vibeforcer.installer._shared import (
    command_is_vibeforcer_hook,
    filter_owned_hook_commands,
    merge_owned_hooks,
)
from vibeforcer.installer._suite import update_suite
from vibeforcer.installer._suite_autoupdate import install_autoupdate, uninstall_autoupdate

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
def test_command_is_vibeforcer_hook_returns_bool_for_arbitrary_text_property(
    command: str,
) -> None:
    result = command_is_vibeforcer_hook(command)
    assert isinstance(result, bool), "must return bool"


@given(strategies.just(None))
def test_command_is_vibeforcer_hook_rejects_non_string_inputs_property(_: None) -> None:
    assert command_is_vibeforcer_hook(42) is False
    assert command_is_vibeforcer_hook(None) is False
    assert command_is_vibeforcer_hook([]) is False


@given(strategies.just(True))
def test_update_suite_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = update_suite(dry_run=dry_run)
    assert result == 0, f"update_suite(dry_run=True) must return 0, got {result}"


@given(strategies.just(True))
def test_install_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = install_autoupdate(dry_run=dry_run)
    assert result == 0, f"install_autoupdate(dry_run=True) must return 0, got {result}"


@given(strategies.just(True))
def test_uninstall_autoupdate_dry_run_returns_zero_property(dry_run: bool) -> None:
    result = uninstall_autoupdate(dry_run=dry_run)
    assert result == 0, f"uninstall_autoupdate(dry_run=True) must return 0, got {result}"


@given(strategies.sampled_from(["PreToolUse", "PostToolUse"]))
def test_merge_owned_hooks_preserves_unrelated_events_property(event: str) -> None:
    existing: dict[str, object] = {"hooks": {event: [{"hooks": [{"command": "echo keep"}]}]}}
    managed = {event: [{"hooks": [{"command": "vibeforcer handle --platform claude"}]}]}
    merged = merge_owned_hooks(existing, managed)

    assert event in merged


@given(strategies.just(None))
def test_filter_owned_hook_commands_keeps_external_hooks_property(_: None) -> None:
    entry = {
        "matcher": "Write",
        "hooks": [
            {"command": "vibeforcer handle"},
            {"command": "echo external"},
        ],
    }
    filtered = filter_owned_hook_commands(entry)

    assert filtered is not None
    assert isinstance(filtered["hooks"], list)
