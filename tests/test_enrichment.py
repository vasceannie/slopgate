"""Tests for the context enrichment pipeline.

Tests use tmp_project to create real filesystem layouts with conftest.py,
sibling test files, and requirements files so enrichment can discover them.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests import support as test_support
from tests.support import LoadFixture

from vibeforcer._types import ObjectDict
from vibeforcer.engine import evaluate_payload
from vibeforcer.enrichment import (
    discover_fixtures,
    find_parametrize_examples,
    enrich_findings,
)
from vibeforcer.enrichment import quality_enrichers
from vibeforcer.models import RuleFinding, Severity


# ===========================================================================
# Helpers
# ===========================================================================


def _mkdir(directory: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
    _ = directory.mkdir(parents=parents, exist_ok=exist_ok)


def _write_text(path: Path, content: str) -> None:
    _ = path.write_text(content, encoding="utf-8")


def _make_conftest(
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
    _write_text(conftest, "\n".join(lines))
    return conftest


def _make_sibling_test(
    directory: Path, name: str, has_parametrize: bool = False
) -> Path:
    """Create a sibling test file, optionally with @pytest.mark.parametrize."""
    if has_parametrize:
        content = (
            "import pytest\n\n"
            '@pytest.mark.parametrize("x,expected", [(1, True), (2, False)])\n'
            "def test_example(x, expected):\n"
            "    assert process(x) == expected\n"
        )
    else:
        content = "def test_simple():\n    assert True\n"
    path = directory / name
    _write_text(path, content)
    return path


def _pretool_write_payload(file_path: str, content: str, cwd: str) -> ObjectDict:
    return {
        "session_id": "test-enrichment",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


# ===========================================================================
# Unit tests: _discover_fixtures
# ===========================================================================


# ===========================================================================
# Unit tests: _find_parametrize_examples
# ===========================================================================


# ===========================================================================
# Integration: PY-TEST-003 enrichment through engine
# ===========================================================================


# ===========================================================================
# Integration: PY-TEST-001 enrichment
# ===========================================================================


# ===========================================================================
# Integration: PY-TEST-004 enrichment
# ===========================================================================


# ===========================================================================
# Integration: PY-TEST-002 enrichment
# ===========================================================================


# ===========================================================================
# Integration: PY-TYPE-001 enrichment
# ===========================================================================


# ===========================================================================
# Safety: enrichment errors don't break the pipeline
# ===========================================================================


# ===========================================================================
# Existing fixture-based tests still pass (regression)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-008 enrichment (long methods)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-009 enrichment (long params)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-013 enrichment (thin wrappers)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-015 enrichment (cyclomatic complexity)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-012 enrichment (feature envy)
# ===========================================================================


# ===========================================================================
# Integration: PY-CODE-013 enrichment (thin wrappers)
# ===========================================================================


# ===========================================================================
# Integration: PY-EXC-002 enrichment (silent exceptions)
# ===========================================================================


# ===========================================================================
# Integration: PY-LOG-001 enrichment (stdlib logger)
# ===========================================================================


# ===========================================================================
# Integration: PY-TYPE-002 enrichment (type suppressions)
# ===========================================================================


# ===========================================================================
# Integration: PY-QUALITY-010 enrichment (magic numbers)
# ===========================================================================


# ===========================================================================
# Integration: PY-QUALITY-009 enrichment (hardcoded paths)
# ===========================================================================

# Exported test support used by split test modules.
__all__ = ('LoadFixture', 'ObjectDict', 'Path', 'RuleFinding', 'Severity', '_make_conftest', '_make_sibling_test', '_mkdir', '_pretool_write_payload', '_write_text', 'discover_fixtures', 'enrich_findings', 'evaluate_payload', 'find_parametrize_examples', 'pytest', 'quality_enrichers', 'test_support', 'time')
