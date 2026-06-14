"""Shared lint collector and hook rule catalog metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeVar

from slopgate.constants import BLOCK, POST_TOOL_USE, PRE_TOOL_USE
from slopgate.lint import _parity
from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.constants import (
    DEFERRED_TEST_INTEGRITY_COLLECTORS,
    TOUCHED_TEST_INTEGRITY_COLLECTORS,
)

CatalogScope = Literal["file", "touched", "project", "suite", "git-base"]
CatalogCost = Literal["cheap", "moderate", "expensive"]
CatalogSurface = Literal["hook", "stop", "cli", "dashboard", "async"]
_CatalogMetadataValue = TypeVar("_CatalogMetadataValue", CatalogScope, CatalogCost)

IMMEDIATE_DUPLICATION_COLLECTORS = frozenset(
    {
        "duplicate-call-sequence",
        "repeated-code-block",
        "repeated-magic-number",
        "repeated-string-literal",
        "semantic-clone",
    }
)
PROJECT_CONSTANT_SCAN_COLLECTORS = frozenset(
    {"repeated-magic-number", "repeated-string-literal"}
)
DEFAULT_COLLECTOR_EVENTS = (POST_TOOL_USE, "Stop", "CLI")


def _assign_collector_metadata(
    target: dict[str, _CatalogMetadataValue],
    collector_ids: frozenset[str],
    value: _CatalogMetadataValue,
) -> None:
    for collector_id in collector_ids:
        target[collector_id] = value


def _collector_metadata_by_id(
    defaults: dict[str, _CatalogMetadataValue],
    assignments: tuple[tuple[frozenset[str], _CatalogMetadataValue], ...],
) -> dict[str, _CatalogMetadataValue]:
    metadata = dict(defaults)
    for collector_ids, value in assignments:
        _assign_collector_metadata(metadata, collector_ids, value)
    return metadata


_COLLECTOR_SCOPE_DEFAULTS: dict[str, CatalogScope] = {"git-base": "git-base"}
_COLLECTOR_SCOPE_ASSIGNMENTS: tuple[tuple[frozenset[str], CatalogScope], ...] = (
    (DEFERRED_TEST_INTEGRITY_COLLECTORS, "suite"),
    (TOUCHED_TEST_INTEGRITY_COLLECTORS, "touched"),
    (PROJECT_CONSTANT_SCAN_COLLECTORS, "project"),
)
_COLLECTOR_COST_ASSIGNMENTS: tuple[tuple[frozenset[str], CatalogCost], ...] = (
    (DEFERRED_TEST_INTEGRITY_COLLECTORS, "expensive"),
    (IMMEDIATE_DUPLICATION_COLLECTORS, "moderate"),
    (PROJECT_CONSTANT_SCAN_COLLECTORS, "moderate"),
)
_COLLECTOR_COST_DEFAULTS: dict[str, CatalogCost] = {}
_COLLECTOR_SCOPES_BY_ID: dict[str, CatalogScope] = _collector_metadata_by_id(
    _COLLECTOR_SCOPE_DEFAULTS, _COLLECTOR_SCOPE_ASSIGNMENTS
)
_COLLECTOR_COSTS_BY_ID: dict[str, CatalogCost] = _collector_metadata_by_id(
    _COLLECTOR_COST_DEFAULTS, _COLLECTOR_COST_ASSIGNMENTS
)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """Catalog metadata for one public hook rule or lint collector ID."""

    stable_id: str
    counterpart_ids: tuple[str, ...]
    scope: CatalogScope
    cost: CatalogCost
    events: tuple[str, ...]
    surfaces: tuple[CatalogSurface, ...]
    default_action: str | None
    deferred_eligible: bool


def _reverse_counterparts() -> dict[str, tuple[str, ...]]:
    counterparts: dict[str, list[str]] = {}
    for rule_id, collector_ids in _parity.HOOK_RULE_BASELINE_COUNTERPARTS.items():
        for collector_id in collector_ids:
            counterparts.setdefault(collector_id, []).append(rule_id)
    return {
        collector_id: tuple(sorted(rule_ids))
        for collector_id, rule_ids in counterparts.items()
    }


def _collector_surfaces(collector_id: str) -> tuple[CatalogSurface, ...]:
    surfaces: tuple[CatalogSurface, ...] = ("cli", "dashboard")
    if collector_id in DEFERRED_TEST_INTEGRITY_COLLECTORS:
        return ("stop", *surfaces)
    return ("hook", *surfaces)


def _collector_events(collector_id: str) -> tuple[str, ...]:
    if collector_id in DEFERRED_TEST_INTEGRITY_COLLECTORS:
        return ("Stop", "CLI")
    return DEFAULT_COLLECTOR_EVENTS


def collector_catalog() -> dict[str, CatalogEntry]:
    """Return catalog metadata for every classified lint collector."""

    reverse_counterparts = _reverse_counterparts()
    return {
        collector_id: CatalogEntry(
            stable_id=collector_id,
            counterpart_ids=reverse_counterparts.get(collector_id, ()),
            scope=_COLLECTOR_SCOPES_BY_ID.get(collector_id, "file"),
            cost=_COLLECTOR_COSTS_BY_ID.get(collector_id, "cheap"),
            events=_collector_events(collector_id),
            surfaces=_collector_surfaces(collector_id),
            default_action=(
                None if collector_id in DEFERRED_TEST_INTEGRITY_COLLECTORS else BLOCK
            ),
            deferred_eligible=collector_id in DEFERRED_TEST_INTEGRITY_COLLECTORS,
        )
        for collector_id in sorted(_parity.classified_collector_keys())
    }


def hook_rule_catalog() -> dict[str, CatalogEntry]:
    """Return catalog metadata for every classified hook/runtime rule."""

    return {
        rule_id: CatalogEntry(
            stable_id=rule_id,
            counterpart_ids=_parity.HOOK_RULE_BASELINE_COUNTERPARTS.get(rule_id, ()),
            scope="touched" if rule_id == "QUALITY-LINT-001" else "file",
            cost="moderate" if rule_id == "QUALITY-LINT-001" else "cheap",
            events=(
                (POST_TOOL_USE,)
                if rule_id == "QUALITY-LINT-001"
                else (PRE_TOOL_USE, POST_TOOL_USE, "Stop")
            ),
            surfaces=("hook", "dashboard"),
            default_action=BLOCK if rule_id == "QUALITY-LINT-001" else None,
            deferred_eligible=False,
        )
        for rule_id in sorted(_parity.classified_hook_rule_ids())
    }


def collector_ids_for_surface(
    surface: CatalogSurface, *, event: str | None = None
) -> frozenset[str]:
    """Return known collector IDs enabled for *surface* and optional event."""

    selected: set[str] = set()
    for collector_id, entry in collector_catalog().items():
        if surface not in entry.surfaces:
            continue
        if event is not None and event not in entry.events:
            continue
        selected.add(collector_id)
    return frozenset(selected)


def filter_cataloged_collectors(
    results: list[tuple[str, list[Violation]]],
    surface: CatalogSurface,
    *,
    event: str | None = None,
) -> list[tuple[str, list[Violation]]]:
    """Filter known collectors through catalog routing while preserving custom IDs."""

    catalog = collector_catalog()
    allowed = collector_ids_for_surface(surface, event=event)
    return [item for item in results if item[0] not in catalog or item[0] in allowed]


__all__ = [
    "CatalogCost",
    "CatalogEntry",
    "CatalogScope",
    "CatalogSurface",
    "DEFAULT_COLLECTOR_EVENTS",
    "IMMEDIATE_DUPLICATION_COLLECTORS",
    "PROJECT_CONSTANT_SCAN_COLLECTORS",
    "collector_catalog",
    "collector_ids_for_surface",
    "filter_cataloged_collectors",
    "hook_rule_catalog",
]
