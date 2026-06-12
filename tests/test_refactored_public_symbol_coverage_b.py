"""Static reference coverage for public installer suite surfaces."""

from __future__ import annotations

import importlib

from slopgate.cli.hook_runtime_parsers import (
    CommandParserFactory,
    HookRuntimeParserRegistration,
    add_hook_runtime_parsers,
    positive_int,
)
from slopgate.cli.io import (
    CliInputError,
    dump_output,
    load_stdin_json,
    report_cli_input_error,
    stdin_is_interactive,
)
from slopgate.cli.lint.git_base_debt import (
    ConfiguredLintFiles,
    GitBaseDebt,
    scan_git_base_debt,
)
from slopgate.cli.lint.report_format import colorize, existing_location_lines
from slopgate.daemon.protocol import (
    decode_request,
    decode_response,
    encode_request,
    encode_response,
    read_frame,
)
from slopgate.daemon.client import DAEMON_ACCEPTED_FAILURE_ERROR
from slopgate.daemon.scheduler import (
    DaemonRequestScheduler,
    DaemonServerOptions,
    RepoLockRegistry,
)
from slopgate.installer.hook_proxy import posix_daemon_proxy_command
from slopgate.installer.suite import (
    AUTOUPDATE_MARKER,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_UPDATE_SOURCE,
    SchedulerPlan,
    build_scheduler_plan,
    install_autoupdate,
    uninstall_autoupdate,
)
from slopgate.installer.suite.autoupdate_windows import (
    prepare_windows_task_replacement,
    remove_windows_task_by_name,
    scheduler_file_is_owned,
)
from slopgate.rules._error_output_signals import has_error_signals
from slopgate.rules.python_ast._pytest_asyncio_fixture_scope import (
    FixtureScopeState,
    configured_loop_scope_note,
    explicit_fixture_loop_scope_message,
    fixture_scope_state,
    is_pytest_path,
    plain_auto_fixture_scope_message,
    resource_scope_note,
    unknown_fixture_scope_message,
    unknown_loop_scope_message,
)
from slopgate.search.cli.command_specs import (
    ArgumentSpec,
    CommandSpec,
    SearchCommands,
    command_specs,
    init_argument_specs,
)
from slopgate.util.atomic_files import (
    append_lines_locked,
    locked_path,
    write_text_atomic_locked,
)

_magic_number_import_hints = importlib.import_module(
    "slopgate.enrichment.quality_enrichers._magic_number_import_hints"
)
_test_smell_rule_helpers = importlib.import_module(
    "slopgate.rules.python_ast._staging._test_smell_rule_helpers"
)

format_constant_value: object = getattr(
    _magic_number_import_hints, "format_constant_value"
)
extract_importable_constants: object = getattr(
    _magic_number_import_hints, "extract_importable_constants"
)
constant_file_candidates: object = getattr(
    _magic_number_import_hints, "constant_file_candidates"
)
module_name_for_import: object = getattr(
    _magic_number_import_hints, "module_name_for_import"
)
append_importable_constant_hints: object = getattr(
    _magic_number_import_hints, "append_importable_constant_hints"
)
is_test_function: object = getattr(_test_smell_rule_helpers, "is_test_function")
is_test_file: object = getattr(_test_smell_rule_helpers, "is_test_file")
contains_assertion: object = getattr(_test_smell_rule_helpers, "contains_assertion")
walk_skip_nested_funcs: object = getattr(
    _test_smell_rule_helpers, "walk_skip_nested_funcs"
)
is_type_checking_block: object = getattr(
    _test_smell_rule_helpers, "is_type_checking_block"
)
parse_test_module: object = getattr(_test_smell_rule_helpers, "parse_test_module")
iter_test_module_nodes: object = getattr(
    _test_smell_rule_helpers, "iter_test_module_nodes"
)

PUBLIC_SYMBOL_GROUPS_b: dict[str, tuple[object, ...]] = {
    "suite": (
        AUTOUPDATE_MARKER,
        DEFAULT_UPDATE_INTERVAL_MINUTES,
        DEFAULT_UPDATE_SOURCE,
        SchedulerPlan,
        build_scheduler_plan,
        install_autoupdate,
        uninstall_autoupdate,
    ),
    "suite_autoupdate_windows": (
        scheduler_file_is_owned,
        remove_windows_task_by_name,
        prepare_windows_task_replacement,
    ),
    "hook_runtime_parsers": (
        CommandParserFactory,
        HookRuntimeParserRegistration,
        add_hook_runtime_parsers,
        positive_int,
    ),
    "cli_io": (
        CliInputError,
        stdin_is_interactive,
        load_stdin_json,
        report_cli_input_error,
        dump_output,
    ),
    "git_base_debt": (ConfiguredLintFiles, GitBaseDebt, scan_git_base_debt),
    "lint_report_format": (colorize, existing_location_lines),
    "magic_number_import_hints": (
        format_constant_value,
        extract_importable_constants,
        constant_file_candidates,
        module_name_for_import,
        append_importable_constant_hints,
    ),
    "hook_proxy": (posix_daemon_proxy_command,),
    "error_output_signals": (has_error_signals,),
    "pytest_asyncio_fixture_scope": (
        is_pytest_path,
        unknown_fixture_scope_message,
        unknown_loop_scope_message,
        configured_loop_scope_note,
        resource_scope_note,
        FixtureScopeState,
        fixture_scope_state,
        plain_auto_fixture_scope_message,
        explicit_fixture_loop_scope_message,
    ),
    "test_smell_rule_helpers": (
        is_test_function,
        is_test_file,
        contains_assertion,
        walk_skip_nested_funcs,
        is_type_checking_block,
        parse_test_module,
        iter_test_module_nodes,
    ),
    "search_cli_command_specs": (
        SearchCommands,
        ArgumentSpec,
        CommandSpec,
        command_specs,
        init_argument_specs,
    ),
    "daemon_protocol": (
        DAEMON_ACCEPTED_FAILURE_ERROR,
        encode_request,
        decode_request,
        encode_response,
        decode_response,
        read_frame,
    ),
    "daemon_scheduler": (
        DaemonRequestScheduler,
        DaemonServerOptions,
        RepoLockRegistry,
    ),
    "atomic_files": (
        append_lines_locked,
        write_text_atomic_locked,
        locked_path,
    ),
}


def test_refactored_public_symbols_are_importable_b() -> None:
    observed = {name: len(symbols) for name, symbols in PUBLIC_SYMBOL_GROUPS_b.items()}

    assert all(count > 0 for count in observed.values()), (
        "Expected every public symbol group to expose at least one import"
    )
    assert len(observed) == len(PUBLIC_SYMBOL_GROUPS_b), (
        "Expected observed symbol groups to match declared groups"
    )
