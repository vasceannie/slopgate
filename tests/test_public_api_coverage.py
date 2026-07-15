from __future__ import annotations

import ast
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies

from slopgate.lint._collector_groups.integrity import full_integrity_collectors
from slopgate.lint._collector_groups.runners import run_all_collectors
from slopgate.lint._config import load_config
from slopgate.lint._detectors.test_smells import (
    build_test_integrity_index,
    detect_coverage_artifact_incomplete,
    detect_possibly_dead_internal,
    detect_untested_public_api,
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


def test_literal_all_limits_normal_module_public_surface() -> None:
    index = build_test_integrity_index(
        [
            _parsed(
                '__all__ = ["included"]\n\ndef included():\n    return 1\n\ndef omitted():\n    return 2\n',
                "src/pkg/module.py",
            )
        ],
        [],
    )

    assert [symbol.name for symbol in index.production_symbols] == ["included"], (
        "literal __all__ should be authoritative for normal modules"
    )


def test_private_module_requires_package_facade_reexport() -> None:
    index = build_test_integrity_index(
        [_parsed("def hidden():\n    return 1\n", "src/pkg/_internal.py")],
        [],
    )

    assert index.production_symbols == [], (
        "unexported definitions in underscore modules are not public API"
    )


def test_facade_reexport_alias_is_public_reference_candidate() -> None:
    index = build_test_integrity_index(
        [
            _parsed("def implementation():\n    return 1\n", "src/pkg/_internal.py"),
            _parsed(
                'from ._internal import implementation as public_name\n__all__ = ["public_name"]\n',
                "src/pkg/__init__.py",
            ),
        ],
        [_parsed("from pkg import public_name\n", "tests/test_api.py")],
    )

    symbol = index.production_symbols[0]
    assert (symbol.name, symbol.reference_names) == (
        "implementation",
        ("pkg.public_name", "public_name"),
    ), "facade aliases should accumulate as public reference candidates"


def test_multiple_facades_accumulate_reference_candidates() -> None:
    index = build_test_integrity_index(
        [
            _parsed("def implementation():\n    return 1\n", "src/pkg/_internal.py"),
            _parsed(
                "from ._internal import implementation as first\n",
                "src/pkg/__init__.py",
            ),
            _parsed(
                "from .._internal import implementation as second\n",
                "src/pkg/api/__init__.py",
            ),
        ],
        [],
    )

    assert index.production_symbols[0].reference_names == (
        "first",
        "pkg.api.second",
        "pkg.first",
        "second",
    ), "every explicit facade alias should remain a valid public reference"


def test_facade_all_excludes_unlisted_reexport() -> None:
    index = build_test_integrity_index(
        [
            _parsed("def implementation():\n    return 1\n", "src/pkg/_internal.py"),
            _parsed(
                'from ._internal import implementation\n__all__ = ["other"]\n',
                "src/pkg/__init__.py",
            ),
        ],
        [],
    )

    assert index.production_symbols == [], (
        "facade __all__ should exclude imported names that are not listed"
    )


def test_dynamic_all_uses_documented_normal_module_fallback() -> None:
    index = build_test_integrity_index(
        [
            _parsed(
                "__all__ = build_exports()\n\ndef conventional_public():\n    return 1\n",
                "src/pkg/module.py",
            )
        ],
        [],
    )

    assert [symbol.name for symbol in index.production_symbols] == [
        "conventional_public"
    ], "unresolvable __all__ should not execute target code"


def test_expected_coverage_paths_include_private_modules_with_top_level_symbols() -> (
    None
):
    index = build_test_integrity_index(
        [
            _parsed("def public():\n    return 1\n", "src/pkg/public.py"),
            _parsed("def private():\n    return 1\n", "src/pkg/_private.py"),
            _parsed("VALUE = 1\n", "src/pkg/constants.py"),
        ],
        [],
    )

    assert index.expected_coverage_paths == (
        "src/pkg/_private.py",
        "src/pkg/public.py",
    ), "expected coverage should use top-level definitions before publicity filtering"


def test_full_collectors_report_public_api_through_alias() -> None:
    parsed_src = [
        _parsed("def implementation():\n    return 1\n", "src/pkg/_internal.py"),
        _parsed(
            'from ._internal import implementation as public_name\n__all__ = ["public_name"]\n',
            "src/pkg/__init__.py",
        ),
    ]
    parsed_tests = [_parsed("from pkg import public_name\n", "tests/test_api.py")]

    collectors = dict(full_integrity_collectors(parsed_src, parsed_tests))

    assert collectors["untested-public-api"] == [], (
        "tests may reference the exported alias instead of the implementation name"
    )


def _dead_internal_source(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    source_file = package / "_internal.py"
    source_file.write_text(
        "def unused_helper():\n    return 1\n",
        encoding="utf-8",
    )
    return source_file


def test_possibly_dead_internal_defaults_off(tmp_path: Path) -> None:
    source_file = _dead_internal_source(tmp_path)
    load_config(tmp_path)

    default_collectors = dict(run_all_collectors([source_file], []))

    assert "possibly-dead-internal" not in default_collectors, (
        "dead internal candidates should default off"
    )


def test_possibly_dead_internal_uses_candidate_wording_when_enabled(
    tmp_path: Path,
) -> None:
    source_file = _dead_internal_source(tmp_path)
    (tmp_path / "slopgate.toml").write_text(
        '[enabled_cli_rules]\n"possibly-dead-internal" = true\n',
        encoding="utf-8",
    )
    load_config(tmp_path)
    enabled_collectors = dict(run_all_collectors([source_file], []))
    candidate = enabled_collectors["possibly-dead-internal"][0]

    assert (
        "candidate" in candidate.detail.lower()
        or "possibly" in candidate.detail.lower()
    ), "dead internal findings must remain advisory rather than claiming proof"


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    symbol_name=strategies.from_regex(
        r"public_[a-z0-9_]{0,8}",
        fullmatch=True,
    )
)
def test_detect_untested_public_api_reports_public_symbol(
    tmp_path: Path,
    symbol_name: str,
) -> None:
    load_config(tmp_path)
    index = build_test_integrity_index(
        [_parsed(f"def {symbol_name}():\n    return 1\n", "src/pkg/public.py")],
        [],
    )

    violations = detect_untested_public_api(index=index)

    assert [violation.rule for violation in violations] == ["untested-public-api"], (
        "the public API detector should report the unreferenced public symbol"
    )


def test_detect_coverage_artifact_incomplete_ignores_absent_artifacts(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    index = build_test_integrity_index(
        [_parsed("def public():\n    return 1\n", "src/pkg/public.py")],
        [],
    )

    violations = detect_coverage_artifact_incomplete(index=index)

    assert violations == [], "absent coverage artifacts should use static fallback"


def test_detect_possibly_dead_internal_reports_private_symbol(tmp_path: Path) -> None:
    load_config(tmp_path)
    index = build_test_integrity_index(
        [_parsed("def unused():\n    return 1\n", "src/pkg/_internal.py")],
        [],
    )

    violations = detect_possibly_dead_internal(index=index)

    assert [violation.rule for violation in violations] == ["possibly-dead-internal"], (
        "the internal detector should report the unreferenced private symbol"
    )


def test_possibly_dead_internal_excludes_production_references(tmp_path: Path) -> None:
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    internal = package / "_internal.py"
    caller = package / "caller.py"
    internal.write_text("def used_helper():\n    return 1\n", encoding="utf-8")
    caller.write_text(
        "from ._internal import used_helper\n\nVALUE = used_helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "slopgate.toml").write_text(
        '[enabled_cli_rules]\n"possibly-dead-internal" = true\n',
        encoding="utf-8",
    )
    load_config(tmp_path)

    collectors = dict(run_all_collectors([internal, caller], []))

    assert collectors["possibly-dead-internal"] == [], (
        "production imports and calls should exclude internal dead-code candidates"
    )
