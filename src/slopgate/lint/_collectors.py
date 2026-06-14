"""Collector registry — runs all detectors and returns (rule_name, violations) pairs.

Pre-parses files once so AST-based detectors share the same parse result.
"""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import ParsedFile, parse_files
from slopgate.lint._parse_errors import detect_python_parse_errors

SourceAnalysis = tuple[
    list[ParsedFile],
    list[ParsedFile],
    list[Violation],
    list[Violation],
]
CollectorResults = list[tuple[str, list[Violation]]]
OPT_IN_CLI_COLLECTORS = frozenset(
    {
        "dead-code",
        "boundary-logging",
        "feature-envy",
        "flat-sibling-files",
        "import-alias",
        "import-fanout",
        "langgraph-deprecated-api",
        "langgraph-state-mutation",
        "langgraph-state-reducer",
        "private-import-chain",
        "pytest-asyncio-pattern",
    }
)


def _collector_enabled(rule_name: str, enabled_cli_rules: dict[str, bool]) -> bool:
    if rule_name in OPT_IN_CLI_COLLECTORS:
        return enabled_cli_rules.get(rule_name, False)
    if not enabled_cli_rules:
        return True
    return enabled_cli_rules.get(rule_name, True)


def _enabled_collectors(collectors: CollectorResults) -> CollectorResults:
    from slopgate.lint._config import get_config

    enabled_cli_rules = get_config().enabled_cli_rules
    return [
        (rule_name, violations)
        for rule_name, violations in collectors
        if _collector_enabled(rule_name, enabled_cli_rules)
    ]


def _ast_src_collectors(
    src_files: list[Path],
    parsed_src: list[ParsedFile],
) -> list[tuple[str, list[Violation]]]:
    """Collect AST-based source violations (type safety, exceptions, logging, etc.)."""
    from slopgate.lint._detectors.exception_safety import (
        detect_broad_except_swallow,
        detect_silent_except,
        detect_silent_fallback,
    )
    from slopgate.lint._detectors.line_length import detect_long_lines
    from slopgate.lint._detectors.langgraph import (
        detect_langgraph_builder_api,
        detect_langgraph_state_mutations,
        detect_langgraph_state_reducers,
    )
    from slopgate.lint._detectors.logging_conventions import (
        detect_boundary_logging,
        detect_direct_get_logger,
        detect_wrong_logger_name,
    )
    from slopgate.lint._detectors.stale_code import detect_stale_patterns
    from slopgate.lint._detectors.type_safety import (
        detect_any_usage,
        detect_type_suppressions,
    )
    from slopgate.lint._detectors.wrappers import detect_unnecessary_wrappers

    return [
        ("unnecessary-wrapper", detect_unnecessary_wrappers(parsed_src)),
        ("deprecated-pattern", detect_stale_patterns(parsed_src)),
        ("langgraph-deprecated-api", detect_langgraph_builder_api(parsed_src)),
        ("langgraph-state-mutation", detect_langgraph_state_mutations(parsed_src)),
        ("langgraph-state-reducer", detect_langgraph_state_reducers(parsed_src)),
        ("boundary-logging", detect_boundary_logging(parsed_src)),
        ("direct-get-logger", detect_direct_get_logger(parsed_src)),
        ("wrong-logger-name", detect_wrong_logger_name(parsed_src)),
        ("banned-any", detect_any_usage(parsed_src)),
        ("type-suppression", detect_type_suppressions(parsed_src)),
        ("broad-except-swallow", detect_broad_except_swallow(parsed_src)),
        ("silent-datetime-fallback", detect_silent_fallback(parsed_src)),
        ("silent-except", detect_silent_except(parsed_src)),
        ("long-line", detect_long_lines(parsed_src)),
    ]


def _structure_src_collectors(
    src_files: list[Path],
    parsed_src: list[ParsedFile],
    oversized: list[Violation],
    literals: list[Violation],
) -> list[tuple[str, list[Violation]]]:
    """Collect structure/complexity/duplicate source violations."""
    from slopgate.lint._detectors.code_smells import (
        detect_deep_nesting,
        detect_god_classes,
        detect_high_complexity,
        detect_long_methods,
        detect_too_many_params,
    )
    from slopgate.lint._detectors.duplicates import (
        detect_duplicate_call_sequences,
        detect_repeated_blocks,
        detect_semantic_clones,
    )
    from slopgate.lint._detectors.source_interop import (
        detect_dead_code,
        detect_feature_envy,
        detect_flat_sibling_files,
        detect_import_aliases,
        detect_import_fanout,
        detect_private_import_chains,
    )

    return [
        ("feature-envy", detect_feature_envy(parsed_src)),
        ("import-fanout", detect_import_fanout(parsed_src)),
        ("import-alias", detect_import_aliases(parsed_src)),
        ("private-import-chain", detect_private_import_chains(parsed_src)),
        ("high-complexity", detect_high_complexity(parsed_src)),
        ("long-method", detect_long_methods(parsed_src)),
        ("too-many-params", detect_too_many_params(parsed_src)),
        ("deep-nesting", detect_deep_nesting(parsed_src)),
        ("god-class", detect_god_classes(parsed_src)),
        ("dead-code", detect_dead_code(parsed_src)),
        ("flat-sibling-files", detect_flat_sibling_files(parsed_src)),
        ("oversized-module", [v for v in oversized if v.rule == "oversized-module"]),
        (
            "oversized-module-soft",
            [v for v in oversized if v.rule == "oversized-module-soft"],
        ),
        ("semantic-clone", detect_semantic_clones(parsed_src)),
        (
            "repeated-magic-number",
            [v for v in literals if v.rule == "repeated-magic-number"],
        ),
        (
            "repeated-string-literal",
            [v for v in literals if v.rule == "repeated-string-literal"],
        ),
        ("repeated-code-block", detect_repeated_blocks(parsed_src)),
        ("duplicate-call-sequence", detect_duplicate_call_sequences(parsed_src)),
    ]


def _test_collectors(
    test_files: list[Path],
    parsed_tests: list[ParsedFile],
) -> list[tuple[str, list[Violation]]]:
    """Collect all test-file violation pairs."""
    from slopgate.lint._detectors.test_smells import (
        detect_assertion_free_tests,
        detect_assertion_roulette,
        detect_conditional_assertions,
        detect_eager_tests,
        detect_fixtures_outside_conftest,
        detect_pytest_asyncio_patterns,
        detect_long_tests,
    )

    return [
        ("long-test", detect_long_tests(parsed_tests)),
        ("eager-test", detect_eager_tests(parsed_tests)),
        ("assertion-free-test", detect_assertion_free_tests(parsed_tests)),
        ("assertion-roulette", detect_assertion_roulette(parsed_tests)),
        ("conditional-assertion", detect_conditional_assertions(parsed_tests)),
        ("fixture-outside-conftest", detect_fixtures_outside_conftest(parsed_tests)),
        ("pytest-asyncio-pattern", detect_pytest_asyncio_patterns(parsed_tests)),
    ]


def test_integrity_collectors(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    *,
    parsed_test_targets: list[ParsedFile] | None = None,
) -> list[tuple[str, list[Violation]]]:
    """Collect bad-test-efficacy and holistic suite-quality indicators."""
    from slopgate.lint._detectors.test_smells import (
        build_test_integrity_index,
        detect_hand_built_test_payloads,
        detect_hypothesis_candidates,
        detect_missing_integration_tests,
        detect_mock_theater,
        detect_mocked_integration_tests,
        detect_stale_test_references,
        detect_schema_bypasses,
        detect_untested_production_code,
        detect_weak_assertions,
    )

    index = build_test_integrity_index(parsed_src, parsed_tests)
    test_targets = parsed_tests if parsed_test_targets is None else parsed_test_targets
    return [
        ("untested-production-code", detect_untested_production_code(index=index)),
        ("missing-integration-test", detect_missing_integration_tests(index=index)),
        ("hypothesis-candidate", detect_hypothesis_candidates(index=index)),
        ("obsolete-or-deprecated-test", detect_stale_test_references(index=index)),
        ("weak-test-assertion", detect_weak_assertions(test_targets)),
        ("mock-theater", detect_mock_theater(test_targets)),
        ("schema-bypass-test-data", detect_schema_bypasses(test_targets)),
        ("hand-built-test-payload", detect_hand_built_test_payloads(test_targets)),
        ("mocked-integration-test", detect_mocked_integration_tests(test_targets)),
    ]


def _source_analysis(
    src_files: list[Path],
    test_files: list[Path],
) -> SourceAnalysis:
    from slopgate.lint._config import get_config
    from slopgate.lint._detectors.code_smells import detect_oversized_modules
    from slopgate.lint._detectors.duplicates import detect_repeated_literals
    from slopgate.quality.constant_index import (
        build_project_constant_index,
        set_session_constant_index,
    )

    parsed_src = parse_files(src_files)
    parsed_tests = parse_files(test_files)
    parsed_all = [*parsed_src, *parsed_tests]
    oversized = detect_oversized_modules(parsed_all)
    constant_index = build_project_constant_index(get_config().project_root)
    set_session_constant_index(constant_index)
    literals = detect_repeated_literals(parsed_src, constant_index=constant_index)
    return parsed_src, parsed_tests, oversized, literals


def run_test_integrity_collectors(
    src_files: list[Path],
    test_files: list[Path],
) -> list[tuple[str, list[Violation]]]:
    """Run focused detectors for bad-test-efficacy indicators only."""

    parsed_src = parse_files(src_files)
    parsed_tests = parse_files(test_files)
    return _enabled_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *test_integrity_collectors(parsed_src, parsed_tests),
        ]
    )


def run_touched_collectors(
    src_files: list[Path],
    test_files: list[Path],
    *,
    reference_test_files: list[Path] | None = None,
) -> list[tuple[str, list[Violation]]]:
    """Run detectors for touched files while using suite tests as references.

    Post-edit hooks should lint only the file(s) a tool just touched, but
    source-oriented test-integrity detectors need the whole test suite as their
    reference corpus. Otherwise every isolated production edit looks untested
    whenever the hook payload lacks the matching test files.
    """
    parsed_src, parsed_tests, oversized, literals = _source_analysis(
        src_files, test_files
    )
    from slopgate.lint._regex_rules import regex_rule_collectors

    parsed_reference_tests = (
        parsed_tests
        if reference_test_files is None
        else parse_files(reference_test_files)
    )

    return _enabled_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *_structure_src_collectors(src_files, parsed_src, oversized, literals),
            *_ast_src_collectors(src_files, parsed_src),
            *_test_collectors(test_files, parsed_tests),
            *regex_rule_collectors(parsed_src, parsed_tests),
            *test_integrity_collectors(
                parsed_src,
                parsed_reference_tests,
                parsed_test_targets=parsed_tests,
            ),
        ]
    )


def run_all_collectors(
    src_files: list[Path],
    test_files: list[Path],
) -> list[tuple[str, list[Violation]]]:
    """Run all detectors and return (rule_name, violations) pairs."""
    parsed_src, parsed_tests, oversized, literals = _source_analysis(
        src_files, test_files
    )
    from slopgate.lint._regex_rules import regex_rule_collectors

    return _enabled_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *_structure_src_collectors(src_files, parsed_src, oversized, literals),
            *_ast_src_collectors(src_files, parsed_src),
            *_test_collectors(test_files, parsed_tests),
            *regex_rule_collectors(parsed_src, parsed_tests),
            *test_integrity_collectors(parsed_src, parsed_tests),
        ]
    )
