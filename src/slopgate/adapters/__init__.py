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
    "OmpAdapter",
    "OpenCodeAdapter",
    "PiAdapter",
]

from slopgate.adapters._session_identity import SESSION_IDENTITY_TELEMETRY
from slopgate.adapters.base import PlatformAdapter
from slopgate.adapters.claude import ClaudeAdapter
from slopgate.adapters.codex import CodexAdapter
from slopgate.adapters.cursor import CursorAdapter
from slopgate.adapters.omp import OmpAdapter
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.adapters.pi import PiAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "cursor": CursorAdapter,
    "omp": OmpAdapter,
    "opencode": OpenCodeAdapter,
    "pi": PiAdapter,
}

_ADAPTER_CACHE: dict[str, PlatformAdapter] = {}


def get_adapter(platform: str) -> PlatformAdapter:
    """Return the singleton adapter instance for the given platform name."""
    SESSION_IDENTITY_TELEMETRY.record_metric("adapter.registry.lookup")
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
