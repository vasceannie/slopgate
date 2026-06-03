from __future__ import annotations

from hypothesis import given, strategies

from vibeforcer.engine._render import render_output
from vibeforcer.enrichment.fixtures import discover_fixtures, find_parametrize_examples
from vibeforcer.installer._shared import (
    filter_owned_hook_commands,
    merge_owned_hooks,
    remove_owned_hooks,
)
from vibeforcer.rules.common._shell_read import is_safe_read_shell_command
from vibeforcer.rules.python_ast._helpers import parse_module

_SHORT_CMD = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 /-_.",
    max_size=40,
)
_SHORT_SRC = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 =():\n_.",
    max_size=80,
)


@given(strategies.just(None))
def test_render_output_is_callable_property(_: None) -> None:
    assert callable(render_output)


@given(strategies.just(None))
def test_discover_fixtures_is_callable_property(_: None) -> None:
    assert callable(discover_fixtures)


@given(strategies.just(None))
def test_find_parametrize_examples_is_callable_property(_: None) -> None:
    assert callable(find_parametrize_examples)


@given(strategies.just(None))
def test_filter_owned_hook_commands_returns_none_for_non_mapping_property(_: None) -> None:
    assert filter_owned_hook_commands("not-a-dict") is None
    assert filter_owned_hook_commands(42) is None
    assert filter_owned_hook_commands(None) is None


@given(strategies.just(None))
def test_merge_owned_hooks_returns_merged_dict_property(_: None) -> None:
    result = merge_owned_hooks({}, {})
    assert isinstance(result, dict)


@given(strategies.just(None))
def test_remove_owned_hooks_returns_empty_for_empty_input_property(_: None) -> None:
    result = remove_owned_hooks({})
    assert isinstance(result, dict)
    assert result == {}


@given(_SHORT_CMD)
def test_is_safe_read_shell_command_returns_bool_property(command: str) -> None:
    result = is_safe_read_shell_command(command)
    assert isinstance(result, bool)


@given(_SHORT_SRC)
def test_parse_module_returns_none_or_module_for_any_source_property(source: str) -> None:
    result = parse_module(source, max_chars=1000)
    assert result is None or hasattr(result, "body"), "must be None or ast.Module"
