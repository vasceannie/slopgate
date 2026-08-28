from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from tests.test_enrichment import (
    RuleFinding,
    Severity,
    make_conftest,
    make_sibling_test,
    mkdir,
    write_text,
)

from slopgate.context import HookContext
from slopgate.enrichment.pytest_enrichers import (
    enrich_assertion_roulette,
    enrich_fixture_outside_conftest,
    enrich_test_loop,
    enrich_test_smells,
)


def _context(root: Path) -> HookContext:
    ctx = SimpleNamespace(config=SimpleNamespace(root=root))
    return cast(HookContext, ctx)


def _enriched_finding(
    root: Path,
    path: str,
    rule_id: str,
    enricher: Callable[[RuleFinding, HookContext], None],
) -> RuleFinding:
    finding = RuleFinding(
        rule_id=rule_id,
        title="test finding",
        severity=Severity.HIGH,
        decision="deny",
        message="base denial",
        metadata={"hits": [path]},
    )
    enricher(finding, _context(root))
    return finding


def _tests_dir(root: Path) -> Path:
    tests_dir = root / "tests"
    mkdir(tests_dir)
    return tests_dir


def _prepare_loop_project(root: Path) -> None:
    tests_dir = _tests_dir(root)
    make_conftest(tests_dir, ["db_session", "data_case"], with_params=["data_case"])
    make_sibling_test(tests_dir, "test_existing.py", has_parametrize=True)
    write_text(tests_dir / "test_target.py", "def test_target():\n    pass\n")


def _prepare_fixture_project(root: Path, fixture: str, filename: str) -> None:
    tests_dir = _tests_dir(root)
    make_conftest(tests_dir, [fixture])
    write_text(tests_dir / filename, "def test_placeholder():\n    pass\n")


def _prepare_time_project(root: Path) -> None:
    tests_dir = _tests_dir(root)
    make_conftest(tests_dir, ["server"])
    write_text(root / "requirements.txt", "freezegun==1.5.1\n")
    write_text(tests_dir / "test_api.py", "def test_api():\n    pass\n")


def test_enrich_test_loop_adds_fixture_parametrize_and_context(tmp_path: Path) -> None:
    _prepare_loop_project(tmp_path)
    finding = _enriched_finding(
        tmp_path,
        "tests/test_target.py",
        "PY-TEST-003",
        enrich_test_loop,
    )

    message = finding.message or ""
    context = finding.additional_context or ""
    evidence = {
        "message:`db_session`": "`db_session`" in message,
        "message:test_existing.py": "test_existing.py" in message,
        "context:no generic block": "COMPLIANT ALTERNATIVES" not in context,
        "context:data_case": "data_case (parametrized)" in context,
    }
    assert evidence == {label: True for label in evidence}, (
        f"Expected bounded local enrichment, got: {evidence}"
    )


def test_enrich_assertion_roulette_adds_fixture_names_and_split_tip(
    tmp_path: Path,
) -> None:
    _prepare_fixture_project(tmp_path, "user_factory", "test_user.py")
    finding = _enriched_finding(
        tmp_path,
        "tests/test_user.py",
        "PY-TEST-001",
        enrich_assertion_roulette,
    )

    message = finding.message or ""
    evidence = {
        "has_message": bool(message),
        "has_fixture": "`user_factory`" in message,
        "has_split_tip": "splitting into focused test functions" in message,
    }
    assert evidence == {label: True for label in evidence}, (
        f"Unexpected assertion-roulette enrichment: {message}"
    )


def test_enrich_test_smells_mentions_fixtures_and_time_utilities(
    tmp_path: Path,
) -> None:
    _prepare_time_project(tmp_path)
    finding = _enriched_finding(
        tmp_path,
        "tests/test_api.py",
        "PY-TEST-002",
        enrich_test_smells,
    )

    message = finding.message or ""
    missing = {
        "`server`": "`server`" not in message,
        "freezegun": "freezegun" not in message,
        "time-control tip": "prefer frozen or polled time controls" not in message,
    }
    assert not {label for label, absent in missing.items() if absent}


def test_enrich_fixture_outside_conftest_suggests_nearest_registry(
    tmp_path: Path,
) -> None:
    write_text(
        _tests_dir(tmp_path) / "test_db.py", "def test_placeholder():\n    pass\n"
    )
    finding = _enriched_finding(
        tmp_path,
        "tests/test_db.py",
        "PY-TEST-004",
        enrich_fixture_outside_conftest,
    )

    message = finding.message or ""
    evidence = {
        "has_message": bool(message),
        "has_registry_path": "No conftest.py exists yet in tests/" in message,
        "has_registry_tip": "Create one as a thin fixture registry" in message,
    }
    assert evidence == {label: True for label in evidence}, (
        f"Unexpected fixture-placement enrichment: {message}"
    )
