from __future__ import annotations

import os
from pathlib import Path

def config_dir() -> Path:
    """Return the vibeforcer config directory.

    Priority:
      1. $VIBEFORCER_CONFIG_DIR
      2. $XDG_CONFIG_HOME/vibeforcer
      3. ~/.config/vibeforcer
    """
    explicit = os.getenv("VIBEFORCER_CONFIG_DIR")
    if explicit:
        return Path(explicit).resolve()
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).resolve() / "vibeforcer"
    return Path.home() / ".config" / "vibeforcer"


def resolve_config_path() -> Path:
    """Resolve the config.json file path.

    Priority:
      1. $VIBEFORCER_CONFIG env var (explicit file path)
      2. config_dir() / config.json
      3. Legacy: $CLAUDE_HOOK_LAYER_ROOT / .claude/hook-layer/config.json
      4. Bundled defaults (resources/defaults.json)
    """
    # Explicit file override
    explicit_file = os.getenv("VIBEFORCER_CONFIG")
    if explicit_file:
        p = Path(explicit_file).resolve()
        if p.exists():
            return p

    # XDG location
    xdg_config = config_dir() / "config.json"
    if xdg_config.exists():
        return xdg_config

    # Legacy hook-layer location
    legacy_root = os.getenv("CLAUDE_HOOK_LAYER_ROOT") or os.getenv("HOOK_LAYER_ROOT")
    if legacy_root:
        legacy_path = Path(legacy_root) / ".claude" / "hook-layer" / "config.json"
        if legacy_path.exists():
            return legacy_path

    # Default legacy location
    legacy_default = (
        Path.home()
        / ".claude"
        / "hooks"
        / "enforcer"
        / ".claude"
        / "hook-layer"
        / "config.json"
    )
    if legacy_default.exists():
        return legacy_default

    # Bundled defaults
    from vibeforcer.resources import resource_path

    return resource_path("defaults.json")


def detect_root() -> Path:
    """Resolve the vibeforcer root directory for traces and prompt context.

    Priority:
      1. $VIBEFORCER_ROOT
      2. config_dir()
      3. Legacy: $CLAUDE_HOOK_LAYER_ROOT / $HOOK_LAYER_ROOT
    """
    explicit = os.getenv("VIBEFORCER_ROOT")
    if explicit:
        return Path(explicit).resolve()

    cfg = config_dir()
    if cfg.exists():
        return cfg

    legacy = os.getenv("CLAUDE_HOOK_LAYER_ROOT") or os.getenv("HOOK_LAYER_ROOT")
    if legacy:
        return Path(legacy).resolve()

    return cfg  # XDG default even if it doesn't exist yet
