from __future__ import annotations

import ast
from pathlib import Path

import pytest

from vibeforcer.lint._helpers import (
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


def test_build_test_integrity_index_caches_shared_symbols_and_references() -> None:
    from vibeforcer.lint._detectors.test_smells._integrity_index import (
        build_test_integrity_index,
    )

    parsed_src, parsed_tests = _sample_inputs()
    index = build_test_integrity_index(parsed_src, parsed_tests)

    assert [symbol.name for symbol in index.production_symbols] == [
        "parse_payload",
        "deprecated_old",
        "orchestrate_event",
    ]
    assert "parse_payload" in index.test_reference_tokens
    assert "pkg.core.parse_payload" in index.test_reference_tokens
    assert "tests/test_core.py" in index.test_reference_tokens_by_rel
    assert index.module_names == {"pkg.core"}
    assert [symbol.name for symbol in index.deprecated_symbols] == ["deprecated_old"]
    assert index.production_call_sites["parse_payload"] == [
        "src/pkg/core.py:11",
        "src/pkg/core.py:12",
    ]


def test_indexed_detectors_do_not_rebuild_production_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.lint._detectors.test_smells._integrity_index import (
        build_test_integrity_index,
    )
    from vibeforcer.lint._detectors.test_smells import _hypothesis_obsolete
    from vibeforcer.lint._detectors.test_smells import _production_detectors

    parsed_src, parsed_tests = _sample_inputs()
    index = build_test_integrity_index(parsed_src, parsed_tests)

    def fail_rebuild(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("detector rebuilt facts already present in TestIntegrityIndex")

    monkeypatch.setattr(_production_detectors, "_production_symbols", fail_rebuild)
    monkeypatch.setattr(_production_detectors, "_production_test_inputs", fail_rebuild)
    monkeypatch.setattr(_production_detectors, "_integration_test_reference_tokens", fail_rebuild)
    monkeypatch.setattr(_production_detectors, "_production_call_sites", fail_rebuild)
    monkeypatch.setattr(_hypothesis_obsolete, "_production_symbols", fail_rebuild)
    monkeypatch.setattr(_hypothesis_obsolete, "_production_test_inputs", fail_rebuild)
    monkeypatch.setattr(_hypothesis_obsolete, "_module_names", fail_rebuild)
    monkeypatch.setattr(_hypothesis_obsolete, "_reference_tokens_for_tree", fail_rebuild)

    _production_detectors.detect_untested_production_code(index=index)
    _production_detectors.detect_missing_integration_tests(index=index)
    _hypothesis_obsolete.detect_hypothesis_candidates(index=index)
    _hypothesis_obsolete.detect_obsolete_or_deprecated_tests(index=index)


def test_test_integrity_collectors_build_one_shared_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.lint import _collectors
    from vibeforcer.lint._detectors import test_smells
    from vibeforcer.lint._detectors.test_smells._integrity_index import (
        build_test_integrity_index,
    )

    parsed_src, parsed_tests = _sample_inputs()
    calls = 0

    def counted_build(src: list[ParsedFile], tests: list[ParsedFile]):
        nonlocal calls
        calls += 1
        return build_test_integrity_index(src, tests)

    monkeypatch.setattr(test_smells, "build_test_integrity_index", counted_build)

    _collectors._test_integrity_collectors(parsed_src, parsed_tests)

    assert calls == 1
