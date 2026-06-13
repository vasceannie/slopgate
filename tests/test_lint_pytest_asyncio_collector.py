from __future__ import annotations

import keyword
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint._detectors.test_smells import detect_pytest_asyncio_patterns
from slopgate.lint._helpers import ParsedFile, parse_files
from slopgate.lint._config import load_config, reset_config

IDENTIFIERS = strategies.from_regex(r"[a-z][a-z_]{0,12}", fullmatch=True).filter(
    lambda value: value not in keyword.kwlist
)


def parsed_file(tmp_path: Path, source: str, name: str) -> list[ParsedFile]:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return parse_files([path])


def parsed_temp_source(source: str, name: str) -> list[ParsedFile]:
    with TemporaryDirectory() as raw_path:
        return parsed_file(Path(raw_path), source, name)


def test_pytest_asyncio_detector_reports_unmarked_async_test(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
async def test_fetches_user():
    assert await fetch_user()
""".lstrip(),
        "tests/test_async_user.py",
    )

    violations = detect_pytest_asyncio_patterns(parsed)
    reset_config()

    assert [(item.rule, item.identifier, item.detail) for item in violations] == [
        (
            "pytest-asyncio-pattern",
            "test_fetches_user",
            "missing-asyncio-mark line=1",
        )
    ], "Strict/default pytest-asyncio mode should require async test markers"


def test_pytest_asyncio_detector_ignores_marked_async_test(tmp_path: Path) -> None:
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
import pytest

@pytest.mark.asyncio
async def test_fetches_user():
    assert await fetch_user()
""".lstrip(),
        "tests/test_async_user.py",
    )

    violations = detect_pytest_asyncio_patterns(parsed)
    reset_config()

    assert violations == [], "Explicitly marked async tests should be accepted"


def test_pytest_asyncio_detector_honors_auto_mode(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.pytest.ini_options]\nasyncio_mode = "auto"\n',
        encoding="utf-8",
    )
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
async def test_fetches_user():
    assert await fetch_user()
""".lstrip(),
        "tests/test_async_user.py",
    )

    violations = detect_pytest_asyncio_patterns(parsed)
    reset_config()

    assert violations == [], "Configured asyncio auto mode should allow async tests"


@given(IDENTIFIERS)
def test_pytest_asyncio_detector_ignores_sync_tests_property(name: str) -> None:
    parsed = parsed_temp_source(
        f"def test_{name}():\n    assert True, 'sanity'\n",
        "test_pytest_asyncio_prop.py",
    )
    assert detect_pytest_asyncio_patterns(parsed) == [], (
        "Synchronous tests should not produce pytest-asyncio findings"
    )
