from __future__ import annotations

import ast
import keyword
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given
from hypothesis import strategies

from tests.test_enrichment_public_api import context_for_source
from vibeforcer.adapters import get_adapter
from vibeforcer.lint import _baseline
from vibeforcer.lint._baseline import Violation, assert_no_new_violations
from vibeforcer.lint._config import load_config, reset_config, set_config
from vibeforcer.lint._details import format_violation_details
from vibeforcer.lint._detectors.duplicates import detect_repeated_blocks
from vibeforcer.lint._detectors.line_length import detect_long_lines
from vibeforcer.lint._detectors.test_smells import (
    detect_fixtures_outside_conftest,
)
from vibeforcer.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import join_messages
from vibeforcer.enrichment import enrich_findings


TEXT_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 _.-"
IDENTIFIERS = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True).filter(
    lambda value: not keyword.iskeyword(value)
)
SHORT_TEXT = strategies.text(
    alphabet=TEXT_ALPHABET,
    max_size=40,
)


def parsed_file(source: str, rel: str = "src/example.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path(rel),
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def configured_long_line_violations(source: str) -> list[Violation]:
    with TemporaryDirectory() as raw_path:
        set_config(load_config(Path(raw_path)))
        try:
            return detect_long_lines([parsed_file(source)])
        finally:
            reset_config()


def configured_fixture_violations(source: str, rel: str) -> list[Violation]:
    with TemporaryDirectory() as raw_path:
        set_config(load_config(Path(raw_path)))
        try:
            return detect_fixtures_outside_conftest([parsed_file(source, rel=rel)])
        finally:
            reset_config()


@given(rule=strategies.sampled_from(["unknown-rule", "manual-rule"]), text=SHORT_TEXT)
def test_enrich_findings_preserves_unknown_rule_property(rule: str, text: str) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), "value = 1\n")
        finding = RuleFinding(rule, "title", Severity.LOW, message=text)
        enrich_findings([finding], ctx)

    assert finding.message == text


@given(stable_id=IDENTIFIERS)
def test_assert_no_new_violations_accepts_baselined_ids_property(stable_id: str) -> None:
    original = _baseline.load_baseline
    violation = Violation("manual-rule", "src/example.py", stable_id)
    _baseline.load_baseline = lambda: {"manual-rule": {violation.stable_id}}
    try:
        result = assert_no_new_violations(
            "manual-rule",
            [violation],
        )
    finally:
        _baseline.load_baseline = original

    assert {
        "new": result.new_violations,
        "fixed": result.fixed_violations,
        "current": result.current_count,
    } == {"new": [], "fixed": [], "current": 1}


@given(identifier=IDENTIFIERS, detail=SHORT_TEXT)
def test_format_violation_details_includes_stable_contract_property(
    identifier: str,
    detail: str,
) -> None:
    violation = Violation("manual-rule", "src/example.py", identifier, detail=detail)

    lines = format_violation_details("manual-rule", violation, status="NEW")

    assert {
        "status": lines[0],
        "stable": any(violation.stable_id in line for line in lines),
        "file": any("src/example.py" in line for line in lines),
    } == {
        "status": "    [NEW] manual-rule",
        "stable": True,
        "file": True,
    }


@given(platform=strategies.sampled_from(["claude", "codex", "opencode"]))
def test_get_adapter_returns_cached_adapter_property(platform: str) -> None:
    first = get_adapter(platform)
    second = get_adapter(platform)

    assert first is second


@given(name=IDENTIFIERS)
def test_detect_repeated_blocks_ignores_single_statement_property(name: str) -> None:
    source = f"{name} = 1\n"

    violations = detect_repeated_blocks([parsed_file(source)])

    assert violations == []


@given(name=IDENTIFIERS)
def test_detect_long_lines_accepts_short_executable_lines_property(name: str) -> None:
    violations = configured_long_line_violations(f"{name} = 1\n")

    assert violations == []


@given(name=IDENTIFIERS)
def test_detect_fixtures_outside_conftest_allows_conftest_property(name: str) -> None:
    source = f"import pytest\n\n@pytest.fixture\ndef {name}():\n    return 1\n"
    violations = configured_fixture_violations(source, rel="tests/conftest.py")

    assert violations == []


@given(message=SHORT_TEXT)
def test_join_messages_includes_only_non_empty_messages_property(message: str) -> None:
    findings = [
        RuleFinding("RULE-1", "first", Severity.HIGH, message=message),
        RuleFinding("RULE-2", "second", Severity.LOW, message=""),
    ]

    joined = join_messages(findings)
    expected = f"[RULE-1 | HIGH] {message}" if message else ""

    assert joined == expected
