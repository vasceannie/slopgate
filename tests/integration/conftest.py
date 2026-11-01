"""Fixture registry for integration tests."""

from __future__ import annotations

import pytest

from tests.integration.real_host_support import (
    HostObservation,
    observe_real_host,
    start_real_host,
)


@pytest.fixture(scope="module")
def real_opencode_host(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> HostObservation:
    """Boot the installed OpenCode once for a test module."""
    root = tmp_path_factory.mktemp("real-opencode-host")
    server, directory = start_real_host(root)
    request.addfinalizer(server.stop)
    return observe_real_host(server, directory, root / "probe.json")
