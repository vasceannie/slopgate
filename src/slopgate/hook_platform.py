"""Shared hook platform provenance for CLI and daemon evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from slopgate.constants import PLATFORM_CLAUDE, PLATFORM_OPENCODE

HOOK_SOURCE_OPENCODE_PLUGIN = "opencode-plugin"


def resolve_hook_platform(
    requested_platform: str, payload: Mapping[str, object]
) -> str:
    """Prefer OpenCode provenance when a Claude-labelled payload is from the plugin shim."""
    if (
        requested_platform.strip().lower() == PLATFORM_CLAUDE
        and payload.get("hook_source") == HOOK_SOURCE_OPENCODE_PLUGIN
    ):
        return PLATFORM_OPENCODE
    return requested_platform
