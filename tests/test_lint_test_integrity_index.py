from __future__ import annotations

import ast
import importlib
from collections.abc import Callable
from pathlib import Path

import pytest

from slopgate.config import load_config
from slopgate.context import HookContext
from slopgate.lint._collector_groups.integrity import (
    full_integrity_collectors,
    touched_integrity_collectors,
)
from slopgate.lint._detectors.test_smells import (
    IntegrityIndex,
    build_test_integrity_index,
    detect_hypothesis_candidates,
    detect_missing_integration_tests,
    detect_stale_test_references,
    detect_untested_production_code,
)
from slopgate.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)
from slopgate.rules.common.quality.lint import collect_touched_lint_failures
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload

TOUCHED_SOURCE_PATH = "src/sample.py"
TOUCHED_SOURCE_CONTENT = "value = 1\n"


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


def _post_tool_context_for_touched_source(tmp_path: Path) -> tuple[HookContext, Path]:
    source_file = tmp_path / TOUCHED_SOURCE_PATH
    source_file.parent.mkdir(parents=True)
    source_file.write_text(TOUCHED_SOURCE_CONTENT, encoding="utf-8")
    config = load_config(
        root=tmp_path,
        repo_root=tmp_path,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    trace = TraceWriter(tmp_path / ".slopgate" / "trace")
    payload = HookPayload(
        {
            "session_id": "test-session",
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": TOUCHED_SOURCE_PATH,
                "content": TOUCHED_SOURCE_CONTENT,
            },
        },
        config,
    )
    return (
        HookContext(
            payload=payload,
            config=config,
            trace=trace,
            state=HookStateStore(trace.trace_dir),
        ),
        source_file.resolve(),
    )


def _record_touched_collector_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[Path], list[Path], object]]:
    captured: list[tuple[list[Path], list[Path], object]] = []

    def fake_run_touched_collectors(
        src_files: list[Path],
        test_files: list[Path],
        *,
        reference_test_files: object = None,
    ) -> list[tuple[str, list[object]]]:
        captured.append((src_files, test_files, reference_test_files))
        return []

    monkeypatch.setattr(
        "slopgate.lint._collectors.run_touched_collectors",
        fake_run_touched_collectors,
    )
    return captured


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
            "slopgate.lint._detectors.test_smells.production_detectors"
        ),
        importlib.import_module(
            "slopgate.lint._detectors.test_smells.hypothesis_obsolete"
        ),
    )

    assert _indexed_detector_results(index) == ([], True, True, True)


def test_test_integrity_collectors_build_one_shared_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.lint._detectors import test_smells

    parsed_src, parsed_tests = _sample_inputs()
    calls = 0

    def counted_build(src: list[ParsedFile], tests: list[ParsedFile]):
        nonlocal calls
        calls += 1
        return build_test_integrity_index(src, tests)

    monkeypatch.setattr(test_smells, "build_test_integrity_index", counted_build)

    full_integrity_collectors(parsed_src, parsed_tests)

    assert calls == 1


def test_run_touched_collectors_skips_suite_wide_integrity_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.lint import _collectors
    from slopgate.lint._detectors import test_smells

    def fail_build(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("touched collectors should not build suite index")

    monkeypatch.setattr(test_smells, "build_test_integrity_index", fail_build)

    immediate_names = {name for name, _violations in touched_integrity_collectors([])}
    touched_runner_names = {
        name for name, _violations in _collectors.run_touched_collectors([], [])
    }
    collector_contract = (
        "untested-production-code" not in touched_runner_names,
        "untested-public-api" not in touched_runner_names,
        "coverage-artifact-incomplete" not in touched_runner_names,
        "possibly-dead-internal" not in touched_runner_names,
        "weak-test-assertion" in touched_runner_names,
        "weak-test-assertion" in immediate_names,
    )

    assert collector_contract == (True, True, True, True, True, True), (
        "Touched collectors should defer suite-wide checks and keep local checks immediate"
    )


def test_collect_touched_lint_failures_skips_reference_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx, source_file = _post_tool_context_for_touched_source(tmp_path)
    captured = _record_touched_collector_inputs(monkeypatch)

    def resolve_source_only(_ctx: HookContext) -> tuple[list[Path], list[Path]]:
        return [source_file], []

    monkeypatch.setattr("slopgate.lint._helpers.test_roots", None)
    monkeypatch.setattr(
        "slopgate.rules.common.quality.lint.resolve_python_candidates",
        resolve_source_only,
    )

    collect_touched_lint_failures(ctx)

    assert captured == [([source_file], [], None)], (
        "Touched lint should call collectors without suite reference files"
    )
