from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint.catalog import (
    CatalogSurface,
    collector_catalog,
    collector_ids_for_surface,
    filter_cataloged_collectors,
    hook_rule_catalog,
)

CATALOG_SURFACES: tuple[CatalogSurface, ...] = (
    "hook",
    "stop",
    "cli",
    "dashboard",
)


def test_shared_collector_catalog_routes_deferred_integrity_to_stop_and_cli() -> None:
    catalog = collector_catalog()
    deferred = catalog["untested-production-code"]
    touched = catalog["weak-test-assertion"]

    assert {
        "deferred_scope": deferred.scope,
        "deferred_surfaces": deferred.surfaces,
        "deferred_events": deferred.events,
        "deferred_action": deferred.default_action,
        "touched_scope": touched.scope,
        "touched_surfaces": touched.surfaces,
    } == {
        "deferred_scope": "suite",
        "deferred_surfaces": ("stop", "cli", "dashboard"),
        "deferred_events": ("Stop", "CLI"),
        "deferred_action": None,
        "touched_scope": "touched",
        "touched_surfaces": ("hook", "cli", "dashboard"),
    }


def test_shared_collector_catalog_preserves_immediate_project_constant_scan() -> None:
    catalog = collector_catalog()
    repeated_magic = catalog["repeated-magic-number"]
    hook_ids = collector_ids_for_surface("hook", event="PostToolUse")

    assert {
        "scope": repeated_magic.scope,
        "cost": repeated_magic.cost,
        "action": repeated_magic.default_action,
        "hook_enabled": "repeated-magic-number" in hook_ids,
        "stop_enabled": "repeated-magic-number" in collector_ids_for_surface("stop"),
    } == {
        "scope": "project",
        "cost": "moderate",
        "action": "block",
        "hook_enabled": True,
        "stop_enabled": False,
    }


def test_catalog_filter_keeps_custom_ids_and_removes_deferred_hook_collectors() -> None:
    filtered = filter_cataloged_collectors(
        [
            ("untested-production-code", []),
            ("weak-test-assertion", []),
            ("custom-regex-rule", []),
        ],
        "hook",
        event="PostToolUse",
    )

    assert [collector_id for collector_id, _ in filtered] == [
        "weak-test-assertion",
        "custom-regex-rule",
    ]


@given(surface=strategies.sampled_from(CATALOG_SURFACES))
def test_collector_ids_for_surface_are_catalog_members(
    surface: CatalogSurface,
) -> None:
    ids = collector_ids_for_surface(surface)
    assert ids <= collector_catalog().keys(), (
        f"collector_ids_for_surface({surface!r}) should return catalog IDs"
    )


@given(custom_id=strategies.text(min_size=1, max_size=16))
def test_filter_cataloged_collectors_preserves_custom_ids(custom_id: str) -> None:
    filtered = filter_cataloged_collectors([(custom_id, [])], "hook")
    assert filtered == [(custom_id, [])], (
        "filter_cataloged_collectors should preserve custom collector IDs"
    )


@given(rule_id=strategies.sampled_from(["QUALITY-LINT-001", "PY-CODE-012"]))
def test_hook_rule_catalog_entries_are_stable(rule_id: str) -> None:
    entry = hook_rule_catalog()[rule_id]
    assert entry.stable_id == rule_id, "hook_rule_catalog should preserve rule IDs"


def test_hook_rule_catalog_links_quality_lint_to_baseline_counterparts() -> None:
    quality_entry = hook_rule_catalog()["QUALITY-LINT-001"]

    assert {
        "scope": quality_entry.scope,
        "events": quality_entry.events,
        "action": quality_entry.default_action,
        "has_counterparts": bool(quality_entry.counterpart_ids),
    } == {
        "scope": "touched",
        "events": ("PostToolUse",),
        "action": "block",
        "has_counterparts": True,
    }
