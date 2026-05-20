from __future__ import annotations

from tests.test_pytest_asyncio_rule import (
    BUNDLE_ROOT,
    PYTEST_ASYNCIO_TEMPLATE,
    Path,
    UNMARKED_CLIENT_TEST,
    _assert_denied_by_pytest_asyncio,
    _evaluate_test_client,
    _pytest_asyncio_denials,
    _repo_root,
    _write_payload,
    _write_pytest_mode,
    evaluate_payload,
    pytest,
    subprocess,
    sys,
    textwrap,
)

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

def test_async_test_requires_pytest_mark_asyncio() -> None:
    code = """
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest.mark.asyncio" in reason

@pytest.mark.parametrize(
    "code",
    [
        """
import pytest

@pytest.mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
        """
import pytest as pt

@pt.mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
        """
from pytest import mark

@mark.asyncio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
        """
import pytest

@pytest.mark.parametrize("path", ["/ready", "/health"], ids=["ready", "health"])
@pytest.mark.asyncio
async def test_fetches_path(path):
    result = await client.fetch(path)
    assert result.ok, f"expected ok result for {path}, got {result!r}"
""",
        """
import pytest
from hypothesis import given, strategies as st

@given(path=st.sampled_from(["/ready", "/health"]))
@pytest.mark.asyncio
async def test_fetches_path(path):
    result = await client.fetch(path)
    assert result.ok, f"expected ok result for {path}, got {result!r}"
""",
        """
import pytest

pytestmark = pytest.mark.asyncio

async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
        """
import pytest

class TestClient:
    pytestmark = pytest.mark.asyncio

    async def test_fetches_client(self):
        result = await client.fetch()
        assert result.ok, f"expected ok result, got {result!r}"
""",
        """
import pytest

@pytest.mark.anyio
async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
        """
import pytest

pytestmark = pytest.mark.trio

async def test_fetches_client():
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
""",
    ],
    ids=[
        "pytest-mark",
        "pytest-alias",
        "from-pytest-mark",
        "parametrize-plus-asyncio",
        "hypothesis-plus-asyncio",
        "module-pytestmark",
        "class-pytestmark",
        "anyio-mark",
        "trio-mark",
    ],
)
def test_marked_async_test_variants_are_compliant(code: str) -> None:
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    assert _pytest_asyncio_denials(result) == []

def test_helper_class_named_non_test_is_not_collected_as_pytest_class() -> None:
    code = """
class Helper:
    async def test_named_helper(self):
        return await load_value()
"""
    result = evaluate_payload(_write_payload("tests/test_client.py", code))

    assert _pytest_asyncio_denials(result) == []

def test_async_fixture_named_test_prefix_is_not_treated_as_test_function() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def test_client():
    return await make_client()
"""
    result = evaluate_payload(_write_payload("tests/conftest.py", code))

    assert _pytest_asyncio_denials(result) == []

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
    test_code = UNMARKED_CLIENT_TEST
    fixture_code = """
import pytest

@pytest.fixture
async def client():
    return await make_client()
"""
    test_result = evaluate_payload(_write_payload("tests/test_client.py", test_code, repo))
    fixture_result = evaluate_payload(_write_payload("tests/conftest.py", fixture_code, repo))

    assert _pytest_asyncio_denials(test_result) == []
    assert _pytest_asyncio_denials(fixture_result) == []

def test_pytest_asyncio_auto_mode_addopts_equals_allows_unmarked_test(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\naddopts = --asyncio-mode=auto\n")
    code = UNMARKED_CLIENT_TEST
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    assert _pytest_asyncio_denials(result) == []

def test_pytest_asyncio_auto_mode_addopts_separate_allows_unmarked_test(
    tmp_path: Path,
) -> None:
    repo = _repo_root(tmp_path, "[pytest]\naddopts = --asyncio-mode auto\n")
    code = UNMARKED_CLIENT_TEST
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    assert _pytest_asyncio_denials(result) == []

@pytest.mark.parametrize(
    ("config_name", "pytest_config"),
    [
        ("pyproject.toml", '[tool.pytest.ini_options]\nasyncio_mode = "auto"\n'),
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
    code = UNMARKED_CLIENT_TEST
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    assert _pytest_asyncio_denials(result) == []

def test_pytest_ini_takes_precedence_over_pyproject_toml(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    _ = (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = \"strict\"\n",
        encoding="utf-8",
    )
    code = UNMARKED_CLIENT_TEST
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    assert _pytest_asyncio_denials(result) == []

def test_empty_pytest_ini_stops_pyproject_toml_fallback(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\n")
    _ = (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = \"auto\"\n",
        encoding="utf-8",
    )
    code = UNMARKED_CLIENT_TEST
    result = evaluate_payload(_write_payload("tests/test_client.py", code, repo))

    reason = _assert_denied_by_pytest_asyncio(result)
    assert "@pytest.mark.asyncio" in reason

def test_pytest_asyncio_config_cache_refreshes_when_config_changes(tmp_path: Path) -> None:
    repo = _repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    code = UNMARKED_CLIENT_TEST
    first_result = _evaluate_test_client(repo, code)
    assert _pytest_asyncio_denials(first_result) == []

    _write_pytest_mode(repo, "strict")
    second_result = _evaluate_test_client(repo, code)

    reason = _assert_denied_by_pytest_asyncio(second_result)
    assert "@pytest.mark.asyncio" in reason
