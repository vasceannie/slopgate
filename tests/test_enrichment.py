"""Tests for the context enrichment pipeline.

Tests use tmp_project to create real filesystem layouts with conftest.py,
sibling test files, and requirements files so enrichment can discover them.
"""

from __future__ import annotations
import time
from pathlib import Path
import pytest
from tests import support
from tests.support import LoadFixture
from slopgate._types import ObjectDict
from slopgate.engine import evaluate_payload
from slopgate.enrichment import (
    discover_fixtures,
    find_parametrize_examples,
    enrich_findings,
)
from slopgate.enrichment import quality_enrichers
from slopgate.models import RuleFinding, Severity


def mkdir(directory: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
    _ = directory.mkdir(parents=parents, exist_ok=exist_ok)


def write_text(path: Path, content: str) -> None:
    _ = path.write_text(content, encoding="utf-8")


def make_conftest(
    directory: Path, fixtures: list[str], with_params: list[str] | None = None
) -> Path:
    """Create a conftest.py with the given fixture names."""
    with_params = with_params or []
    lines = ["import pytest\n"]
    for name in fixtures:
        if name in with_params:
            lines.append(
                f"@pytest.fixture(params=[1, 2, 3])\ndef {name}(request):\n    return request.param\n\n"
            )
        else:
            lines.append(f"@pytest.fixture\ndef {name}():\n    return 'value'\n\n")
    conftest = directory / "conftest.py"
    write_text(conftest, "\n".join(lines))
    return conftest


def make_sibling_test(
    directory: Path, name: str, has_parametrize: bool = False
) -> Path:
    """Create a sibling test file, optionally with @pytest.mark.parametrize."""
    if has_parametrize:
        content = 'import pytest\n\n@pytest.mark.parametrize("x,expected", [(1, True), (2, False)])\ndef test_example(x, expected):\n    assert process(x) == expected\n'
    else:
        content = "def test_simple():\n    assert True\n"
    path = directory / name
    write_text(path, content)
    return path


def pretool_write_payload(file_path: str, content: str, cwd: str) -> ObjectDict:
    return {
        "session_id": "test-enrichment",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


__all__ = (
    "LoadFixture",
    "ObjectDict",
    "Path",
    "RuleFinding",
    "Severity",
    "make_conftest",
    "make_sibling_test",
    "mkdir",
    "pretool_write_payload",
    "write_text",
    "discover_fixtures",
    "enrich_findings",
    "evaluate_payload",
    "find_parametrize_examples",
    "pytest",
    "quality_enrichers",
    "support",
    "time",
)
