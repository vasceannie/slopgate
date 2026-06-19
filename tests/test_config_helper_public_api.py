from __future__ import annotations

from hypothesis import given, strategies

from slopgate.config._python_runtime import (
    PythonRuntimeSettings,
    python_runtime_settings,
)
from slopgate.config._rule_surfaces import merge_rule_surfaces, rule_surface_configs
from slopgate.models import CliSurfaceConfig, HookSurfaceConfig, RuleSurfaceConfig

_BASE_SURFACE_CLI_DISABLED = RuleSurfaceConfig(
    hook=HookSurfaceConfig(enabled=False),
    cli=CliSurfaceConfig(enabled=False),
)
_BASE_SURFACE_CLI_ENABLED = RuleSurfaceConfig(
    hook=HookSurfaceConfig(enabled=False),
    cli=CliSurfaceConfig(enabled=True),
)
_OVERRIDE_SURFACE_HOOK_ENABLED = RuleSurfaceConfig(
    hook=HookSurfaceConfig(enabled=True)
)


def test_python_runtime_settings_reads_threshold_overrides() -> None:
    settings = python_runtime_settings(
        {"python_ast": {"enabled": False}},
        {"max_complexity": 7, "max_line_length": 99},
    )

    assert isinstance(settings, PythonRuntimeSettings), (
        "python_runtime_settings should return the public settings value object"
    )
    assert settings.ast_enabled is False, (
        "python_runtime_settings should preserve python_ast enabled override"
    )
    assert settings.max_complexity == 7, (
        "python_runtime_settings should read numeric threshold overrides"
    )
    assert settings.max_line_length == 99, (
        "python_runtime_settings should read line-length threshold overrides"
    )


def test_rule_surface_configs_merge_hook_and_cli_overrides() -> None:
    base = rule_surface_configs(
        {"PY-001": {"hook": {"enabled": True}, "cli": {"enabled": False}}}
    )
    override = rule_surface_configs(
        {"PY-001": {"hook": {"events": ["Stop"], "action": "block"}}}
    )
    merged = merge_rule_surfaces(base, override)

    assert merged == {
        "PY-001": RuleSurfaceConfig(
            hook=HookSurfaceConfig(enabled=True, events=("Stop",), action="block"),
            cli=CliSurfaceConfig(enabled=False),
        )
    }, "merge_rule_surfaces should preserve base values and apply override fields"


@given(
    max_complexity=strategies.integers(min_value=1, max_value=50),
    max_line_length=strategies.integers(min_value=60, max_value=240),
    ast_enabled=strategies.booleans(),
)
def test_python_runtime_settings_preserves_numeric_and_boolean_invariants(
    max_complexity: int, max_line_length: int, ast_enabled: bool
) -> None:
    settings = python_runtime_settings(
        {"python_ast": {"enabled": ast_enabled}},
        {"max_complexity": max_complexity, "max_line_length": max_line_length},
    )

    assert settings == PythonRuntimeSettings(
        ast_enabled=ast_enabled,
        max_complexity=max_complexity,
        max_nesting_depth=settings.max_nesting_depth,
        max_god_class_methods=settings.max_god_class_methods,
        max_line_length=max_line_length,
        feature_envy_threshold=settings.feature_envy_threshold,
        feature_envy_min_accesses=settings.feature_envy_min_accesses,
        import_fanout_limit=settings.import_fanout_limit,
        long_method_lines=settings.long_method_lines,
        long_parameter_limit=settings.long_parameter_limit,
        max_parse_chars=settings.max_parse_chars,
    ), "python_runtime_settings should round-trip explicit threshold invariants"


@given(base_cli_enabled=strategies.booleans())
def test_merge_rule_surfaces_preserves_unoverridden_cli_invariant(
    base_cli_enabled: bool,
) -> None:
    base = {
        "PY-001": (
            _BASE_SURFACE_CLI_ENABLED
            if base_cli_enabled
            else _BASE_SURFACE_CLI_DISABLED
        )
    }
    override = {"PY-001": _OVERRIDE_SURFACE_HOOK_ENABLED}

    merged = merge_rule_surfaces(base, override)

    assert merged["PY-001"].cli.enabled is base_cli_enabled, (
        "merge_rule_surfaces should preserve base CLI settings absent an override"
    )
