from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from vibeforcer._types import object_dict, string_value
from vibeforcer.engine import evaluate_payload
from vibeforcer.models import EngineResult
from vibeforcer.rules.python_ast._pytest_asyncio_messages import PYTEST_ASYNCIO_TEMPLATE

BUNDLE_ROOT = Path(__file__).resolve().parents[1]


def _write_payload(path: str, code: str, cwd: Path | None = None) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": code},
        "cwd": str(cwd or BUNDLE_ROOT),
    }


def _repo_root(
    tmp_path: Path,
    pytest_config: str = "",
    *,
    config_name: str = "pytest.ini",
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    if pytest_config:
        _ = (repo / config_name).write_text(pytest_config, encoding="utf-8")
    return repo


def test_pytest_asyncio_config_import_falls_back_to_tomli_without_tomllib() -> None:
    script = r'''
import builtins
import importlib
import sys

real_import = builtins.__import__

def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "tomllib":
        raise ModuleNotFoundError("No module named 'tomllib'")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = fake_import
sys.modules.pop("tomllib", None)
sys.modules.pop("vibeforcer.rules.python_ast._pytest_asyncio_config", None)
module = importlib.import_module("vibeforcer.rules.python_ast._pytest_asyncio_config")
assert module.pytest_asyncio_mode
'''
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=BUNDLE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_guidance_template_includes_session_scoped_resource_pattern() -> None:
    assert '@pytest_asyncio.fixture(scope="session", loop_scope="session")' in PYTEST_ASYNCIO_TEMPLATE
    assert "async def shared_async_client" in PYTEST_ASYNCIO_TEMPLATE
    assert "not version-dependent" in PYTEST_ASYNCIO_TEMPLATE


def _permission_decision(result: EngineResult) -> str | None:
    assert result.output is not None, "expected hook output"
    specific = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(specific.get("permissionDecision"))
    if decision is not None:
        return decision
    inner = object_dict(specific.get("decision"))
    return string_value(inner.get("behavior"))


def _permission_reason(result: EngineResult) -> str:
    assert result.output is not None, "expected hook output"
    specific = object_dict(result.output.get("hookSpecificOutput"))
    reason = string_value(specific.get("permissionDecisionReason"))
    if reason is not None:
        return reason
    inner = object_dict(specific.get("decision"))
    return string_value(inner.get("message")) or ""


def _assert_denied_by_pytest_asyncio(result: EngineResult) -> str:
    assert _permission_decision(result) == "deny"
    reason = _permission_reason(result)
    assert "PY-TEST-005" in reason
    assert "pytest-asyncio" in reason
    return reason


def _assert_not_denied_by_pytest_asyncio(result: EngineResult) -> None:
    py_test_005_denials = [
        finding
        for finding in result.findings
        if finding.rule_id == "PY-TEST-005" and finding.decision in {"deny", "block"}
    ]
    assert py_test_005_denials == []


def test_async_test_requires_pytest_mark_asyncio() -> None:
    code = """
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest.mark.asyncio" in reason


def test_marked_async_test_is_compliant() -> None:
    code = """
import pytest

@pytest.mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_pytest_alias_marked_async_test_is_compliant() -> None:
    code = """
import pytest as pt

@pt.mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_from_pytest_mark_asyncio_is_compliant() -> None:
    code = """
from pytest import mark

@mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_parametrized_marked_async_test_is_compliant() -> None:
    code = """
import pytest

@pytest.mark.parametrize("path", ["/ready", "/health"], ids=["ready", "health"])
@pytest.mark.asyncio
async def test_fetches_path(path):
    result = await client.fetch(path)
    assert result.ok, f"expected ok result for {path}, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_hypothesis_marked_async_test_is_compliant() -> None:
    code = """
import pytest
from hypothesis import given, strategies as st

@given(path=st.sampled_from(["/ready", "/health"]))
@pytest.mark.asyncio
async def test_fetches_path(path):
    result = await client.fetch(path)
    assert result.ok, f"expected ok result for {path}, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_module_pytestmark_asyncio_is_compliant() -> None:
    code = """
import pytest

pytestmark = pytest.mark.asyncio

async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_class_pytestmark_asyncio_is_compliant() -> None:
    code = """
import pytest

class TestClient:
    pytestmark = pytest.mark.asyncio

    async def test_fetches_client(self):
        result = await client.fetch()
        assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_anyio_marked_async_test_is_compliant() -> None:
    code = """
import pytest

@pytest.mark.anyio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_trio_marked_async_test_is_compliant() -> None:
    code = """
import pytest

pytestmark = pytest.mark.trio

async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_helper_class_named_non_test_is_not_collected_as_pytest_class() -> None:
    code = """
class Helper:
    async def test_named_helper(self):
        return await load_value()
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_async_fixture_named_test_prefix_is_not_treated_as_test_function() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def test_client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_async_fixture_uses_pytest_asyncio_fixture() -> None:
    code = """
import pytest

@pytest.fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest_asyncio.fixture" in reason


def test_pytest_asyncio_auto_mode_allows_plain_async_fixture_and_unmarked_test(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    test_code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    fixture_code = """
import pytest

@pytest.fixture
async def client():
    return await make_client()
"""
    test_result = evaluate_payload(_write_payload("tests/test_client.py", test_code, repo))
    fixture_result = evaluate_payload(_write_payload("tests/conftest.py", fixture_code, repo))

    _assert_not_denied_by_pytest_asyncio(test_result)
    _assert_not_denied_by_pytest_asyncio(fixture_result)


def test_pytest_asyncio_auto_mode_addopts_equals_allows_unmarked_test(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\naddopts = --asyncio-mode=auto\n")
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


def test_pytest_asyncio_auto_mode_addopts_separate_allows_unmarked_test(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\naddopts = --asyncio-mode auto\n")
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


@pytest.mark.parametrize(
    ("config_name", "pytest_config"),
    [
        (
            "pyproject.toml",
            '[tool.pytest.ini_options]\nasyncio_mode = "auto"\n',
        ),
        ("tox.ini", "[pytest]\nasyncio_mode = auto\n"),
        ("setup.cfg", "[tool:pytest]\nasyncio_mode = auto\n"),
    ],
)
def test_auto_mode_config_files_allow_unmarked_test(
    tmp_path: Path,
    config_name: str,
    pytest_config: str,
) -> None:
    repo = _repo_root(tmp_path, pytest_config, config_name=config_name)
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


def test_pytest_ini_takes_precedence_over_pyproject_toml(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    _ = (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = \"strict\"\n",
        encoding="utf-8",
    )
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


def test_empty_pytest_ini_stops_pyproject_toml_fallback(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\n")
    _ = (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = \"auto\"\n",
        encoding="utf-8",
    )
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest.mark.asyncio" in reason


def test_pytest_asyncio_config_cache_refreshes_when_config_changes(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    code = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    first_result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))
    _assert_not_denied_by_pytest_asyncio(first_result)

    _ = (repo / "pytest.ini").write_text("[pytest]\nasyncio_mode = strict\n", encoding="utf-8")
    second_result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    reason = _assert_denied_by_pytest_asyncio(second_result)
    assert "@pytest.mark.asyncio" in reason


def test_auto_mode_wider_plain_async_fixture_gets_pytest_asyncio_loop_scope_guidance(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    code = """
import pytest

@pytest.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code, repo))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest_asyncio.fixture" in reason
    assert 'loop_scope="session"' in reason


def test_pytest_config_default_fixture_loop_scope_satisfies_session_fixture(
    tmp_path: Path,
) -> None:
    repo = _repo_root(
        tmp_path,
        "[pytest]\nasyncio_default_fixture_loop_scope = session\n",
    )
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


def test_narrow_configured_default_fixture_loop_scope_gets_guidance(
    tmp_path: Path,
) -> None:
    repo = _repo_root(
        tmp_path,
        "[pytest]\nasyncio_default_fixture_loop_scope = module\n",
    )
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code, repo))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "asyncio_default_fixture_loop_scope = module" in reason
    assert 'loop_scope="session"' in reason


def test_auto_mode_plain_async_session_fixture_allows_configured_loop_scope(
    tmp_path: Path,
) -> None:
    repo = _repo_root(
        tmp_path,
        "[pytest]\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = session\n",
    )
    code = """
import pytest

@pytest.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code, repo))

    _assert_not_denied_by_pytest_asyncio(result)


def test_pytest_asyncio_fixture_without_yield_is_compliant() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_from_pytest_fixture_async_fixture_is_denied_in_strict_mode() -> None:
    code = """
from pytest import fixture

@fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest_asyncio.fixture" in reason


def test_from_pytest_asyncio_fixture_is_compliant() -> None:
    code = """
from pytest_asyncio import fixture

@fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_function_scoped_async_yield_fixture_keeps_isolation_by_default() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_wider_async_fixture_scope_requires_matching_loop_scope() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert 'loop_scope="session"' in reason
    assert "same as or broader" in reason


def test_module_scoped_async_yield_fixture_is_compliant_with_module_loop_scope() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_session_scoped_async_yield_fixture_is_compliant() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    _assert_not_denied_by_pytest_asyncio(result)


def test_unknown_explicit_fixture_loop_scope_gets_guidance() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session", loop_scope="forever")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "Unknown pytest-asyncio fixture loop_scope" in reason
    assert "forever" in reason


def test_unknown_explicit_fixture_scope_gets_guidance() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="forever", loop_scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "Unknown pytest-asyncio fixture scope" in reason
    assert "forever" in reason


def test_non_test_async_code_is_not_targeted() -> None:
    code = """
async def test_named_helper():
    return await load_value()
"""
    result = evaluate_payload(_write_payload("src/helpers.py", code))

    _assert_not_denied_by_pytest_asyncio(result)
