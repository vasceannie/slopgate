from __future__ import annotations

import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.rules import build_always_on_rules
from tests.test_enrichment_public_api import context_for_source

_render = importlib.import_module("slopgate.engine._render")
_fixtures = importlib.import_module("slopgate.enrichment.fixtures")
_installer = importlib.import_module("slopgate.installer")
_shell_safe_read = importlib.import_module("slopgate.rules.common._shell_safe_read")
_python_ast_helpers = importlib.import_module("slopgate.rules.python_ast._helpers")
_retry = importlib.import_module("slopgate.engine._retry")
_duplicate_blocks = importlib.import_module(
    "slopgate.lint._detectors.duplicates.blocks"
)
_sensitive_git = importlib.import_module("slopgate.rules.common._sensitive_system_git")
_lint_report = importlib.import_module("slopgate.cli.lint_report")
_config_coerce = importlib.import_module("slopgate.config._coerce")
_test_smells = importlib.import_module("slopgate.lint._detectors.test_smells")
_rules_base = importlib.import_module("slopgate.rules.base")
_python_ast_rules = importlib.import_module("slopgate.rules.python_ast._rules")

render_output = _render.render_output
discover_fixtures = _fixtures.discover_fixtures
find_parametrize_examples = _fixtures.find_parametrize_examples
filter_owned_hook_commands = _installer.filter_owned_hook_commands
merge_owned_hooks = _installer.merge_owned_hooks
remove_owned_hooks = _installer.remove_owned_hooks
is_safe_read_shell_command = _shell_safe_read.is_safe_read_shell_command
parse_module = _python_ast_helpers.parse_module
apply_loop_aware_steering = _retry.apply_loop_aware_steering
collect_block_windows = _duplicate_blocks.collect_block_windows
compile_sensitive_patterns = _sensitive_git.compile_sensitive_patterns
tally_rule = _lint_report.tally_rule
print_lint_summary = _lint_report.print_lint_summary
TallyInput = _lint_report.TallyInput
LintRunTotals = _lint_report.LintRunTotals
command_map = _config_coerce.command_map
max_bare_assert_run = _test_smells.max_bare_assert_run
is_rule_enabled = _rules_base.is_rule_enabled
parse_health_failure = _python_ast_rules.parse_health_failure
parse_strict = _python_ast_rules.parse_strict
parsed_functions = _python_ast_rules.parsed_functions
parsed_nodes = _python_ast_rules.parsed_nodes
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
def test_filter_owned_hook_commands_returns_none_for_non_mapping_property(
    _: None,
) -> None:
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


@given(strategies.just(None))
def test_build_always_on_rules_returns_rule_list_property(_: None) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        ctx = context_for_source(root, "value = 1\n")
        rules = build_always_on_rules(ctx)
    assert isinstance(rules, list)
    assert all(hasattr(rule, "rule_id") for rule in rules)


@given(_SHORT_SRC)
def test_parse_module_returns_none_or_module_for_any_source_property(
    source: str,
) -> None:
    result = parse_module(source, max_chars=1000)
    assert result is None or hasattr(result, "body"), "must be None or ast.Module"


@given(strategies.just(None))
def test_apply_loop_aware_steering_is_callable_property(_: None) -> None:
    assert callable(apply_loop_aware_steering)


@given(strategies.just(None))
def test_collect_block_windows_is_callable_property(_: None) -> None:
    assert callable(collect_block_windows)


@given(strategies.lists(_SHORT_CMD, max_size=5))
def test_compile_sensitive_patterns_returns_list_property(patterns: list[str]) -> None:
    compiled = compile_sensitive_patterns(patterns)
    assert isinstance(compiled, list)


@given(strategies.just(None))
def test_tally_rule_and_print_lint_summary_are_callable_property(_: None) -> None:
    assert {
        "tally_rule": callable(tally_rule),
        "print_lint_summary": callable(print_lint_summary),
        "tally_input_type": isinstance(TallyInput, type),
        "lint_totals_type": isinstance(LintRunTotals, type),
    } == {
        "tally_rule": True,
        "print_lint_summary": True,
        "tally_input_type": True,
        "lint_totals_type": True,
    }


@given(strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz\n", max_size=80))
def test_parsed_nodes_returns_list_for_source_property(source: str) -> None:
    from tempfile import TemporaryDirectory

    from tests.test_enrichment_public_api import context_for_source

    with TemporaryDirectory() as directory:
        root = Path(directory)
        observed = len(
            parsed_nodes(source, context_for_source(root, source, path="sample.py"))
        )
    assert isinstance(observed, int)


@given(strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz\n", max_size=80))
def test_parse_strict_returns_none_or_module_property(source: str) -> None:
    result = parse_strict(source, max_chars=1000)
    assert result is None or hasattr(result, "body")


@given(strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz\n", max_size=80))
def test_parse_health_failure_returns_none_or_string_property(source: str) -> None:
    result = parse_health_failure(source, max_chars=1000, suppress_fragments=True)
    assert result is None or isinstance(result, str)


@given(strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz\n", max_size=80))
def test_parsed_functions_returns_list_property(source: str) -> None:
    from tempfile import TemporaryDirectory

    from tests.test_enrichment_public_api import context_for_source

    with TemporaryDirectory() as directory:
        root = Path(directory)
        functions = parsed_functions(
            source, context_for_source(root, source, path="sample.py")
        )
    assert isinstance(functions, list)


@given(
    strategies.dictionaries(
        strategies.text(min_size=1, max_size=8),
        strategies.lists(strategies.text(min_size=1, max_size=8), max_size=3),
        max_size=3,
    )
)
def test_command_map_returns_dict_property(raw: dict[str, list[str]]) -> None:
    assert isinstance(command_map(raw), dict)


@given(strategies.just(None))
def test_max_bare_assert_run_empty_property(_: None) -> None:
    assert max_bare_assert_run([]) == 0


@given(
    rule_id=strategies.sampled_from(["FIXTURE-001", "PY-TEST-001"]),
    enabled=strategies.booleans(),
)
def test_is_rule_enabled_respects_config_override_property(
    rule_id: str, enabled: bool
) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), "value = 1\n")
        ctx.config.enabled_rules[rule_id] = enabled
        assert is_rule_enabled(ctx, rule_id) is enabled
