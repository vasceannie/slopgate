"""Platform adapters for the slopgate engine.

Each adapter translates between a specific CLI tool's hook protocol
and the enforcer's internal canonical representation.

Supported platforms:
  - claude   : Anthropic Claude Code (default)
  - codex    : OpenAI Codex CLI
  - opencode : OpenCode (Anomaly)
  - cursor   : Cursor native hooks
"""

from __future__ import annotations

__all__ = [
    "PlatformAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "OpenCodeAdapter",
    "PiAdapter",
]

from slopgate.adapters.base import PlatformAdapter
from slopgate.adapters.claude import ClaudeAdapter
from slopgate.adapters.codex import CodexAdapter
from slopgate.adapters.cursor import CursorAdapter
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.adapters.pi import PiAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "cursor": CursorAdapter,
    "opencode": OpenCodeAdapter,
    "pi": PiAdapter,
}

_ADAPTER_CACHE: dict[str, PlatformAdapter] = {}


def get_adapter(platform: str) -> PlatformAdapter:
    """Return the singleton adapter instance for the given platform name."""
    cached = _ADAPTER_CACHE.get(platform)
    if cached is not None:
        return cached
    cls = ADAPTERS.get(platform)
    if cls is None:
        valid_options = ", ".join(sorted(ADAPTERS))
        raise ValueError(
            f"Unknown platform {platform!r}. Valid options: {valid_options}"
        )
    instance = cls()
    _ADAPTER_CACHE[platform] = instance
    return instance
