from __future__ import annotations

PYTEST_ASYNCIO_TEMPLATE = """Use pytest-asyncio patterns that match the project config and fixture lifetime:

    import pytest
    import pytest_asyncio

    @pytest.mark.asyncio
    async def test_round_trip(client):
        result = await client.fetch()
        assert result.ok, f"Expected ok result, got {result!r}"

    @pytest_asyncio.fixture(scope="session", loop_scope="session")
    async def shared_async_client():
        client = await connect_client()
        try:
            yield client
        finally:
            await client.aclose()

In default/strict pytest-asyncio mode, async tests need an asyncio marker and
async fixtures need `pytest_asyncio.fixture`. If project config explicitly sets
`asyncio_mode = auto`, pytest-asyncio will add markers and convert plain async
`pytest.fixture` functions automatically.

Do not force session-scoped loops just because a fixture is async. Function scope
keeps isolation. Use broader loop scopes only when a fixture's cache scope or a
costly e2e/integration resource deliberately needs sharing. Declare that
loop_scope explicitly (or via `asyncio_default_fixture_loop_scope`) so behavior is
not version-dependent; configured fixture loop scope must be the same as or
broader than the fixture scope.
"""
