"""Structure and duplicate source collector specs."""

from __future__ import annotations

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.scheduling import CollectorSpec, execute_all
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import ParsedFile


def structure_src_collector_specs(
    parsed_src: list[ParsedFile],
    oversized: list[Violation],
    literals: list[Violation],
    file_local_src: list[ParsedFile] | None = None,
) -> list[CollectorSpec]:
    """Return deferred structure, complexity, and duplicate collectors."""
    local_src = parsed_src if file_local_src is None else file_local_src
    return [
        *_interop_specs(local_src),
        *_smell_specs(local_src),
        *_module_size_specs(oversized),
        *_duplicate_specs(parsed_src, literals),
    ]


def structure_src_collectors(
    parsed_src: list[ParsedFile],
    oversized: list[Violation],
    literals: list[Violation],
) -> CollectorResults:
    """Collect structure/complexity/duplicate source violations."""
    return execute_all(structure_src_collector_specs(parsed_src, oversized, literals))


def _interop_specs(parsed_src: list[ParsedFile]) -> list[CollectorSpec]:
    from slopgate.lint._detectors.source_interop import (
        detect_dead_code,
        detect_feature_envy,
        detect_flat_sibling_files,
        detect_import_aliases,
        detect_import_fanout,
        detect_private_import_chains,
    )

    return [
        CollectorSpec("feature-envy", lambda: detect_feature_envy(parsed_src)),
        CollectorSpec("import-fanout", lambda: detect_import_fanout(parsed_src)),
        CollectorSpec("import-alias", lambda: detect_import_aliases(parsed_src)),
        CollectorSpec("private-import-chain", lambda: detect_private_import_chains(parsed_src)),
        CollectorSpec("dead-code", lambda: detect_dead_code(parsed_src)),
        CollectorSpec("flat-sibling-files", lambda: detect_flat_sibling_files(parsed_src)),
    ]


def _smell_specs(parsed_src: list[ParsedFile]) -> list[CollectorSpec]:
    from slopgate.lint._detectors.code_smells import (
        detect_deep_nesting,
        detect_god_classes,
        detect_high_complexity,
        detect_long_methods,
        detect_too_many_params,
    )

    return [
        CollectorSpec("high-complexity", lambda: detect_high_complexity(parsed_src)),
        CollectorSpec("long-method", lambda: detect_long_methods(parsed_src)),
        CollectorSpec("too-many-params", lambda: detect_too_many_params(parsed_src)),
        CollectorSpec("deep-nesting", lambda: detect_deep_nesting(parsed_src)),
        CollectorSpec("god-class", lambda: detect_god_classes(parsed_src)),
    ]


def _module_size_specs(oversized: list[Violation]) -> list[CollectorSpec]:
    return [
        CollectorSpec(
            "oversized-module",
            lambda: [item for item in oversized if item.rule == "oversized-module"],
        ),
        CollectorSpec(
            "oversized-module-soft",
            lambda: [item for item in oversized if item.rule == "oversized-module-soft"],
        ),
    ]


def _duplicate_specs(
    parsed_src: list[ParsedFile], literals: list[Violation]
) -> list[CollectorSpec]:
    del parsed_src
    return [
        CollectorSpec(
            "semantic-clone",
            lambda: [item for item in literals if item.rule == "semantic-clone"],
        ),
        CollectorSpec(
            "repeated-magic-number",
            lambda: [item for item in literals if item.rule == "repeated-magic-number"],
        ),
        CollectorSpec(
            "repeated-string-literal",
            lambda: [item for item in literals if item.rule == "repeated-string-literal"],
        ),
        CollectorSpec(
            "repeated-code-block",
            lambda: [item for item in literals if item.rule == "repeated-code-block"],
        ),
        CollectorSpec(
            "duplicate-call-sequence",
            lambda: [item for item in literals if item.rule == "duplicate-call-sequence"],
        ),
    ]
