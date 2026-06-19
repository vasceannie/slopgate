"""Rule surface config parsing and merge helpers."""

from __future__ import annotations

from slopgate.constants import RULE_SURFACE_DECISIONS
from slopgate.models import CliSurfaceConfig, HookSurfaceConfig, RuleSurfaceConfig

from ._coerce import object_dict, string_list, string_value


def _hook_surface_config(value: object) -> HookSurfaceConfig:
    data = object_dict(value)
    enabled = data.get("enabled")
    events = tuple(string_list(data.get("events")))
    action = string_value(data.get("action")).strip().lower()
    return HookSurfaceConfig(
        enabled=enabled if isinstance(enabled, bool) else None,
        events=events,
        action=action if action in RULE_SURFACE_DECISIONS else None,
    )


def _cli_surface_config(value: object) -> CliSurfaceConfig:
    data = object_dict(value)
    enabled = data.get("enabled")
    return CliSurfaceConfig(enabled=enabled if isinstance(enabled, bool) else None)


def rule_surface_configs(value: object) -> dict[str, RuleSurfaceConfig]:
    surfaces: dict[str, RuleSurfaceConfig] = {}
    for rule_id, item in object_dict(value).items():
        data = object_dict(item)
        surfaces[rule_id] = RuleSurfaceConfig(
            hook=_hook_surface_config(data.get("hook")),
            cli=_cli_surface_config(data.get("cli")),
        )
    return surfaces


def merge_rule_surfaces(
    base: dict[str, RuleSurfaceConfig], override: dict[str, RuleSurfaceConfig]
) -> dict[str, RuleSurfaceConfig]:
    merged = dict(base)
    for rule_id, surface in override.items():
        current = merged.get(rule_id, RuleSurfaceConfig())
        merged[rule_id] = RuleSurfaceConfig(
            hook=HookSurfaceConfig(
                enabled=(
                    current.hook.enabled
                    if surface.hook.enabled is None
                    else surface.hook.enabled
                ),
                events=surface.hook.events or current.hook.events,
                action=surface.hook.action or current.hook.action,
            ),
            cli=CliSurfaceConfig(
                enabled=(
                    current.cli.enabled
                    if surface.cli.enabled is None
                    else surface.cli.enabled
                )
            ),
        )
    return merged
