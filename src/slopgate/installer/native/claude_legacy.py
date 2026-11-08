"""Scope-safe removal and rollback of prior Claude hook settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    merge_owned_hooks,
    remove_owned_hooks,
    require_contained_install_path,
    write_contained_json,
)
from slopgate.installer.native.artifacts import unsafe_anchor_issue
from slopgate.installer.native.migration import extract_owned_hooks
from slopgate.installer.native.model import (
    HOOKS_KEY,
    LegacyCutover,
    LegacyRefusal,
    NativeRequest,
)

if TYPE_CHECKING:
    from slopgate.installer.native.claude import ClaudeLayout

__all__ = ["ClaudeLegacyCutover"]

_CLAUDE_SETTINGS_LABEL = "Claude settings"


def _settings_path(scope: str, request: NativeRequest, layout: ClaudeLayout) -> Path:
    if scope == INSTALL_SCOPE_PROJECT:
        return layout.project_settings(request.root)
    return layout.user_settings()


def _scope_root(scope: str, request: NativeRequest, layout: ClaudeLayout) -> Path:
    if scope == INSTALL_SCOPE_PROJECT:
        return request.root
    return layout.user_root()


def _read_settings(path: Path, scope: str) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyRefusal(
            f"Refusing to modify unreadable Claude settings for {scope} scope at "
            f"{path}: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise LegacyRefusal(
            f"Refusing to modify Claude settings that are not a JSON object: {path}"
        )
    return cast(dict[str, object], parsed)


def _validate_hooks(settings: dict[str, object], path: Path) -> None:
    if HOOKS_KEY not in settings:
        return
    hooks = settings[HOOKS_KEY]
    if not isinstance(hooks, dict):
        raise LegacyRefusal(
            f"Refusing malformed Claude hooks in {path}: hooks must be an object"
        )
    for event, entries in cast(dict[str, object], hooks).items():
        if not isinstance(entries, list):
            raise LegacyRefusal(
                f"Refusing malformed Claude hooks in {path}: {event} must be a list"
            )
        for entry in cast(list[object], entries):
            if not isinstance(entry, dict):
                raise LegacyRefusal(
                    f"Refusing malformed Claude hooks in {path}: invalid hook group"
                )
            entry_dict = cast(dict[str, object], entry)
            if HOOKS_KEY not in entry_dict:
                continue
            commands = entry_dict[HOOKS_KEY]
            if not isinstance(commands, list):
                raise LegacyRefusal(
                    f"Refusing malformed Claude hooks in {path}: commands must be a list"
                )
            if any(
                not isinstance(command, dict)
                for command in cast(list[object], commands)
            ):
                raise LegacyRefusal(
                    f"Refusing malformed Claude hooks in {path}: invalid command entry"
                )


def _contained_path(scope: str, request: NativeRequest, layout: ClaudeLayout) -> Path:
    path = _settings_path(scope, request, layout)
    root = _scope_root(scope, request, layout)
    try:
        return require_contained_install_path(path, root)
    except UnsafeInstallPathError as exc:
        raise LegacyRefusal(str(exc)) from exc


class ClaudeLegacyCutover(LegacyCutover):
    """Remove only Slopgate-owned hook commands from Claude settings documents."""

    def __init__(self, request: NativeRequest, layout: ClaudeLayout) -> None:
        self._request = request
        self._layout = layout
        self._owned: dict[str, dict[str, list[dict[str, object]]]] = {}
        self._removed: list[str] = []
        self._captured = False

    def preflight(self) -> None:
        for scope in self._request.scopes:
            if scope == INSTALL_SCOPE_PROJECT:
                issue = unsafe_anchor_issue(self._request.root / ".claude")
                if issue:
                    raise LegacyRefusal(issue)
            path = _contained_path(scope, self._request, self._layout)
            settings = _read_settings(path, scope)
            _validate_hooks(settings, path)

    def describe(self) -> list[str]:
        lines: list[str] = []
        for scope in self._request.scopes:
            path = _settings_path(scope, self._request, self._layout)
            settings = _read_settings(path, scope)
            if extract_owned_hooks(settings.get(HOOKS_KEY)):
                lines.append(
                    f"Would remove Slopgate-owned Claude hooks from {path} ({scope} scope)"
                )
            else:
                lines.append(
                    f"No Slopgate-owned Claude hooks in {path} ({scope} scope)"
                )
        return lines

    def capture(self) -> None:
        for scope in self._request.scopes:
            path = _settings_path(scope, self._request, self._layout)
            settings = _read_settings(path, scope)
            self._owned[scope] = extract_owned_hooks(settings.get(HOOKS_KEY))
        self._captured = True

    def remove(self, scope: str) -> int:
        path = _settings_path(scope, self._request, self._layout)
        try:
            settings = _read_settings(path, scope)
            hooks = settings.get(HOOKS_KEY)
            if not extract_owned_hooks(hooks):
                return 0
            remaining = remove_owned_hooks(hooks)
            if remaining:
                settings[HOOKS_KEY] = remaining
            else:
                settings.pop(HOOKS_KEY, None)
            _ = write_contained_json(
                path,
                settings,
                root=_scope_root(scope, self._request, self._layout),
                label=_CLAUDE_SETTINGS_LABEL,
            )
        except (LegacyRefusal, UnsafeInstallPathError, OSError) as exc:
            print(str(exc))
            return 1
        self._removed.append(scope)
        print(f"Removed Slopgate-owned Claude hooks from {path} ({scope} scope)")
        return 0

    def restore(self) -> int:
        if not self._captured:
            return 0
        status = 0
        for scope in reversed(self._removed):
            owned = self._owned.get(scope, {})
            if not owned:
                continue
            path = _settings_path(scope, self._request, self._layout)
            try:
                settings = _read_settings(path, scope)
                merged = merge_owned_hooks(settings.get(HOOKS_KEY), owned)
                if merged:
                    settings[HOOKS_KEY] = merged
                else:
                    settings.pop(HOOKS_KEY, None)
                _ = write_contained_json(
                    path,
                    settings,
                    root=_scope_root(scope, self._request, self._layout),
                    label=_CLAUDE_SETTINGS_LABEL,
                )
            except (LegacyRefusal, UnsafeInstallPathError, OSError) as exc:
                print(f"Failed to restore Claude hooks in {path}: {exc}")
                status = 1
        return status
