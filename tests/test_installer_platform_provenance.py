from __future__ import annotations

import shlex

import pytest

import slopgate.installer._shared


@pytest.mark.parametrize("platform", ["claude", "codex", "cursor"])
def test_posix_hook_fallback_preserves_platform(platform: str) -> None:
    command = slopgate.installer._shared.hook_command(
        "/opt/slopgate/bin/slopgate",
        "handle",
        "--platform",
        platform,
        windows=False,
    )

    argv = shlex.split(command)

    assert argv[3:] == [
        "slopgate-hook",
        "/opt/slopgate/bin/slopgate",
        "handle",
        "--platform",
        platform,
    ], "Proxy fallback should preserve the configured platform"
