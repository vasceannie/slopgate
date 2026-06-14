from __future__ import annotations

import ast
import importlib
from collections.abc import Callable
from pathlib import Path

import pytest

from slopgate.lint._detectors.test_smells import (
    detect_hypothesis_candidates,
    detect_missing_integration_tests,
    detect_stale_test_references,
    detect_untested_production_code,
)
from slopgate.lint._detectors.test_smells._integrity_index import (
    IntegrityIndex,
    build_test_integrity_index,
)
from slopgate.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)


def _parsed(source: str, rel: str) -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path("/tmp/project") / rel,
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def _sample_inputs() -> tuple[list[ParsedFile], list[ParsedFile]]:
    parsed_src = [
        _parsed(
            "def parse_payload(value):\n"
            "    if value:\n"
            "        return value.strip().lower()\n"
            "    return ''\n"
            "\n"
            "def deprecated_old():\n"
            "    '''Deprecated. Use parse_payload instead.'''\n"
            "    return ''\n"
            "\n"
            "def orchestrate_event(value):\n"
            "    parse_payload(value)\n"
            "    return parse_payload(value)\n",
            "src/pkg/core.py",
        )
    ]
    parsed_tests = [
        _parsed(
            "from pkg.core import deprecated_old, parse_payload\n"
            "\n"
            "def test_parse_payload_contract():\n"
            "    assert parse_payload(' Hi ') == 'hi'\n"
            "\n"
            "def test_deprecated_old_contract():\n"
            "    assert deprecated_old() == ''\n",
            "tests/test_core.py",
        )
    ]
    return parsed_src, parsed_tests


def _block_index_rebuild_helpers(
    monkeypatch: pytest.MonkeyPatch,
    fail_rebuild: Callable[..., object],
    production_detectors: object,
    hypothesis_obsolete: object,
) -> None:
    for module, names in (
        (
            production_detectors,
            (
                "production_symbols",
                "production_test_inputs",
                "integration_test_reference_tokens",
            ),
        ),
        (
            hypothesis_obsolete,
            (
                "production_symbols",
                "production_test_inputs",
                "module_names",
                "reference_tokens_for_tree",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(module, name, fail_rebuild)


def _indexed_detector_results(
    index: IntegrityIndex,
) -> tuple[object, bool, bool, bool]:
    untested = detect_untested_production_code(index=index)
    missing_integration = detect_missing_integration_tests(index=index)
    hypothesis_candidates = detect_hypothesis_candidates(index=index)
    deprecated_tests = detect_stale_test_references(index=index)
    return (
        untested,
        bool(missing_integration),
        bool(hypothesis_candidates),
        bool(deprecated_tests),
    )


def test_build_test_integrity_index_caches_shared_symbols_and_references() -> None:
    parsed_src, parsed_tests = _sample_inputs()
    index = build_test_integrity_index(parsed_src, parsed_tests)

    index_contract = (
        [symbol.name for symbol in index.production_symbols],
        {"parse_payload", "pkg.core.parse_payload"}.issubset(
            index.test_reference_tokens
        ),
        "tests/test_core.py" in index.test_reference_tokens_by_rel,
        index.module_names,
        [symbol.name for symbol in index.deprecated_symbols],
        index.production_call_sites["parse_payload"],
    )
    assert index_contract == (
        ["parse_payload", "deprecated_old", "orchestrate_event"],
        True,
        True,
        {"pkg.core"},
        ["deprecated_old"],
        ["src/pkg/core.py:11", "src/pkg/core.py:12"],
    )


def test_indexed_detectors_do_not_rebuild_production_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed_src, parsed_tests = _sample_inputs()
    index = build_test_integrity_index(parsed_src, parsed_tests)

    def fail_rebuild(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("detector rebuilt facts already present in IntegrityIndex")

    _block_index_rebuild_helpers(
        monkeypatch,
        fail_rebuild,
        importlib.import_module(
            "slopgate.lint._detectors.test_smells._production_detectors"
        ),
        importlib.import_module(
            "slopgate.lint._detectors.test_smells._hypothesis_obsolete"
        ),
    )

    assert _indexed_detector_results(index) == ([], True, True, True)


def test_test_integrity_collectors_build_one_shared_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.lint import _collectors
    from slopgate.lint._detectors import test_smells

    parsed_src, parsed_tests = _sample_inputs()
    calls = 0

    def counted_build(src: list[ParsedFile], tests: list[ParsedFile]):
        nonlocal calls
        calls += 1
        return build_test_integrity_index(src, tests)

    monkeypatch.setattr(test_smells, "build_test_integrity_index", counted_build)

    _collectors.test_integrity_collectors(parsed_src, parsed_tests)

    assert calls == 1
