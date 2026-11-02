"""OpenCode plugin scaffold rendering."""

from __future__ import annotations

from slopgate.resources import resource_path

_PLUGIN_RESOURCE = resource_path("opencode_isx_plugin.ts")


def render_opencode_plugin() -> str:
    """Render the OpenCode plugin TypeScript source."""
    return _PLUGIN_RESOURCE.read_text(encoding="utf-8")
