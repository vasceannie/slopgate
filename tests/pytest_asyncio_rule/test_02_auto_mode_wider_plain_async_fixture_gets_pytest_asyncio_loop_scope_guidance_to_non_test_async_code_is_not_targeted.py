from __future__ import annotations

from tests.test_pytest_asyncio_rule import (
    Path,
    assert_denied_by_pytest_asyncio,
    pytest_asyncio_denials,
    repo_root,
    write_payload,
    evaluate_payload,
)


def test_auto_mode_wider_plain_async_fixture_gets_pytest_asyncio_loop_scope_guidance(
    tmp_path: Path,
) -> None:
    repo = repo_root(tmp_path, "[pytest]\nasyncio_mode = auto\n")
    code = """
import pytest

@pytest.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code, repo))

    reason = assert_denied_by_pytest_asyncio(result)
    assert "@pytest_asyncio.fixture" in reason
    assert 'loop_scope="session"' in reason


def test_pytest_config_default_fixture_loop_scope_satisfies_session_fixture(
    tmp_path: Path,
) -> None:
    repo = repo_root(
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
    result = evaluate_payload(write_payload("tests/conftest.py", code, repo))

    assert pytest_asyncio_denials(result) == []


def test_narrow_configured_default_fixture_loop_scope_gets_guidance(
    tmp_path: Path,
) -> None:
    repo = repo_root(
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
    result = evaluate_payload(write_payload("tests/conftest.py", code, repo))

    reason = assert_denied_by_pytest_asyncio(result)
    assert "asyncio_default_fixture_loop_scope = module" in reason
    assert 'loop_scope="session"' in reason


def test_auto_mode_plain_async_session_fixture_allows_configured_loop_scope(
    tmp_path: Path,
) -> None:
    repo = repo_root(
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
    result = evaluate_payload(write_payload("tests/conftest.py", code, repo))

    assert pytest_asyncio_denials(result) == []


def test_pytest_asyncio_fixture_without_yield_is_compliant() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    assert pytest_asyncio_denials(result) == []


def test_from_pytest_fixture_async_fixture_is_denied_in_strict_mode() -> None:
    code = """
from pytest import fixture

@fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    reason = assert_denied_by_pytest_asyncio(result)
    assert "@pytest_asyncio.fixture" in reason


def test_from_pytest_asyncio_fixture_is_compliant() -> None:
    code = """
from pytest_asyncio import fixture

@fixture
async def client():
    return await make_client()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    assert pytest_asyncio_denials(result) == []


def test_function_scoped_async_yield_fixture_keeps_isolation_by_default() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    assert pytest_asyncio_denials(result) == []


def test_wider_async_fixture_scope_requires_matching_loop_scope() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    reason = assert_denied_by_pytest_asyncio(result)
    assert 'loop_scope="session"' in reason
    assert "same as or broader" in reason


def test_module_scoped_async_yield_fixture_is_compliant_with_module_loop_scope() -> (
    None
):
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    assert pytest_asyncio_denials(result) == []


def test_session_scoped_async_yield_fixture_is_compliant() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    assert pytest_asyncio_denials(result) == []


def test_unknown_explicit_fixture_loop_scope_gets_guidance() -> None:
    code = """
import pytest_asyncio

@pytest_asyncio.fixture(scope="session", loop_scope="forever")
async def client():
    client = await make_client()
    yield client
    await client.aclose()
"""
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    reason = assert_denied_by_pytest_asyncio(result)
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
    result = evaluate_payload(write_payload("tests/conftest.py", code))

    reason = assert_denied_by_pytest_asyncio(result)
    assert "Unknown pytest-asyncio fixture scope" in reason
    assert "forever" in reason


def test_non_test_async_code_is_not_targeted() -> None:
    code = """
async def test_named_helper():
    return await load_value()
"""
    result = evaluate_payload(write_payload("src/helpers.py", code))

    assert pytest_asyncio_denials(result) == []
