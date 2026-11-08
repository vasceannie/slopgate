from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .native import (
    CLAUDE_ID,
    OMP_ID,
    claude_registration,
    omp_registration,
    package_root,
    pi_settings,
    pi_settings_path,
    run_host,
)
from .sandbox import Sandbox, SmokeFailure


def set_native_enabled(sandbox: Sandbox, host: str, scope: str, enabled: bool) -> None:
    action = "enable" if enabled else "disable"
    if host == "omp":
        run_host(sandbox, host, ["plugin", action, "--scope", scope, OMP_ID])
        return
    if host == "claude":
        run_host(sandbox, host, ["plugin", action, "--scope", scope, CLAUDE_ID])
        return
    raise SmokeFailure(f"Native enable/disable command is not defined for {host}")


def _claude_user_enabled(sandbox: Sandbox) -> bool:
    settings_path = sandbox.home / ".claude" / "settings.json"
    if not settings_path.exists():
        return True
    try:
        parsed: object = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SmokeFailure(f"Cannot read Claude user enablement: {error}") from error
    if not isinstance(parsed, dict):
        raise SmokeFailure("Claude user settings are not a JSON object")
    settings = cast(dict[str, object], parsed)
    enabled_plugins = settings.get("enabledPlugins")
    if enabled_plugins is None:
        return True
    if not isinstance(enabled_plugins, dict):
        raise SmokeFailure("Claude enabledPlugins setting is not a JSON object")
    enabled = cast(dict[str, object], enabled_plugins).get(CLAUDE_ID, True)
    if not isinstance(enabled, bool):
        raise SmokeFailure("Claude Slopgate enabledPlugins entry is not boolean")
    return enabled


def native_enabled(sandbox: Sandbox, host: str, scope: str) -> bool:
    if host == "omp":
        registration = omp_registration(sandbox, scope)
        if registration is None:
            raise SmokeFailure(f"OMP {scope} registration is missing")
        return registration.get("enabled") is not False
    if host == "claude":
        registration = claude_registration(sandbox, scope)
        if registration is None:
            raise SmokeFailure(f"Claude {scope} registration is missing")
        if scope == "user":
            return _claude_user_enabled(sandbox)
        state = registration.get("projectEnabled", registration.get("enabled", True))
        if not isinstance(state, bool):
            raise SmokeFailure("Claude project enablement is not boolean")
        return state
    raise SmokeFailure(f"Native enable state is not defined for {host}")


def _entry_source(entry: object, scope: str) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        source = cast(dict[str, object], entry).get("source")
        if isinstance(source, str):
            return source
    raise SmokeFailure(f"Pi {scope} package entry has no source: {entry!r}")


def _resolved_source(entry: object, scope: str, settings_path: Path) -> Path:
    source = Path(_entry_source(entry, scope)).expanduser()
    if not source.is_absolute():
        source = settings_path.parent / source
    return source.resolve()


def capture_pi_entry(sandbox: Sandbox, scope: str) -> object:
    settings_path = pi_settings_path(sandbox, scope)
    packages = pi_settings(sandbox, scope).get("packages", [])
    if not isinstance(packages, list):
        raise SmokeFailure(f"Pi {scope} package declarations are malformed")
    expected = package_root(sandbox, "pi").resolve()
    matches = [
        entry
        for entry in cast(list[object], packages)
        if _resolved_source(entry, scope, settings_path) == expected
    ]
    if len(matches) != 1:
        raise SmokeFailure(f"Pi {scope} must contain one Slopgate package declaration")
    return matches[0]


def set_pi_extensions(
    sandbox: Sandbox, scope: str, original_entry: object, extensions: list[str] | None
) -> None:
    settings_path = pi_settings_path(sandbox, scope)
    settings = pi_settings(sandbox, scope)
    packages_value = settings.get("packages", [])
    if not isinstance(packages_value, list):
        raise SmokeFailure(f"Pi {scope} package declarations are malformed")
    packages = cast(list[object], packages_value)
    expected = package_root(sandbox, "pi").resolve()
    selected = [
        index
        for index, entry in enumerate(packages)
        if _resolved_source(entry, scope, settings_path) == expected
    ]
    if len(selected) != 1:
        raise SmokeFailure(f"Pi {scope} Slopgate package declaration disappeared")
    index = selected[0]
    if extensions is None:
        packages[index] = original_entry
    else:
        current = packages[index]
        updated: dict[str, object]
        if isinstance(current, dict):
            updated = dict(cast(dict[str, object], current))
        elif isinstance(current, str):
            updated = {"source": current}
        else:
            raise SmokeFailure(f"Pi {scope} package declaration is malformed")
        updated["extensions"] = extensions
        packages[index] = updated
    settings["packages"] = packages
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
