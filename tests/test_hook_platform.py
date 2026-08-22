from __future__ import annotations

import pytest

from slopgate.constants import PLATFORM_CLAUDE, PLATFORM_CURSOR, PLATFORM_OPENCODE
from slopgate.hook_platform import HOOK_SOURCE_OPENCODE_PLUGIN, resolve_hook_platform


@pytest.mark.parametrize(
    ("requested_platform", "payload", "expected"),
    [
        pytest.param(
            PLATFORM_CLAUDE,
            {"hook_source": HOOK_SOURCE_OPENCODE_PLUGIN},
            PLATFORM_OPENCODE,
            id="claude_plugin_source_remaps",
        ),
        pytest.param(
            "Claude",
            {"hook_source": HOOK_SOURCE_OPENCODE_PLUGIN},
            PLATFORM_OPENCODE,
            id="mixed_case_claude_plugin_source_remaps",
        ),
        pytest.param(
            PLATFORM_CLAUDE,
            {},
            PLATFORM_CLAUDE,
            id="claude_without_source_stays",
        ),
        pytest.param(
            PLATFORM_OPENCODE,
            {"hook_source": HOOK_SOURCE_OPENCODE_PLUGIN},
            PLATFORM_OPENCODE,
            id="opencode_plugin_source_stays",
        ),
        pytest.param(
            PLATFORM_CURSOR,
            {"hook_source": HOOK_SOURCE_OPENCODE_PLUGIN},
            PLATFORM_CURSOR,
            id="cursor_plugin_source_stays",
        ),
    ],
)
def test_resolve_hook_platform(
    requested_platform: str,
    payload: dict[str, object],
    expected: str,
) -> None:
    resolved = resolve_hook_platform(requested_platform, payload)
    assert resolved == expected, (
        f"resolve_hook_platform({requested_platform!r}, {payload!r}) "
        f"should return {expected!r}"
    )
