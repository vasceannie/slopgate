"""Doc-derived schema/context contract for harness docs used by Slopgate tests.

Regenerate with:
python3 <skill>/scripts/harness_schema_context.py --write-tests --format markdown

These tests bind a generated fixture to official-source metadata, source-specific
doc evidence, and Slopgate's adapter contracts. They are not a replacement for
focused behavior tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from slopgate._types import (
    ObjectDict,
    is_object_dict,
    object_dict,
    object_list,
)
from tests.harness_schema_support import (
    assert_installed_sources_are_extractable,
    assert_official_source,
    expected_contract_cross_check,
    opencode_schema_summary_observed,
    opencode_stop_output_summary,
    permission_request_output_summary,
    pretool_output_summary,
    schema_event_map_contract_summary,
    strings,
)
from slopgate.adapters import ADAPTERS
from slopgate.adapters.codex import CODEX_EVENTS
from slopgate.adapters.opencode import OPENCODE_EVENT_MAP, OpenCodeAdapter
from slopgate.installer import CLAUDE_EVENTS
from slopgate.models import RuleFinding, Severity

EXPECTED_CLAUDE_OFFICIAL_EVENTS = set(
    """
    SessionStart Setup CwdChanged UserPromptSubmit UserPromptExpansion PreToolUse
    PermissionRequest PermissionDenied PostToolUse PostToolUseFailure PostToolBatch
    SubagentStart SubagentStop TaskCreated TaskCompleted Stop StopFailure TeammateIdle
    PreCompact PostCompact SessionEnd Elicitation ElicitationResult InstructionsLoaded
    ConfigChange WorktreeCreate WorktreeRemove Notification FileChanged
    """.split()
)

REQUIRED_SOURCES = {
    "claude_hooks": ("claude", "hooks_doc"),
    "claude_settings": ("claude", "settings_doc"),
    "opencode_config_schema": ("opencode", "json_schema"),
    "opencode_config_docs": ("opencode", "config_doc"),
    "opencode_plugin_docs": ("opencode", "plugin_doc"),
    "codex_hooks": ("codex", "hooks_doc"),
    "codex_config_reference": ("codex", "config_reference"),
    "codex_config_advanced": ("codex", "config_advanced"),
}

REQUIRED_SOURCE_KEYWORDS = {
    "claude_hooks": {"PreToolUse", "PermissionRequest", "hookSpecificOutput"},
    "opencode_plugin_docs": {
        "tool.execute.before",
        "tool.execute.after",
        "permission.asked",
        "session.idle",
    },
    "codex_hooks": {"codex_hooks", "PreToolUse", "PermissionRequest"},
}

EXPECTED_OPENCODE_SCHEMA_DEFS = {
    "Config",
    "PermissionActionConfig",
    "PermissionConfig",
    "PermissionRuleConfig",
}

LOCAL_PATH_FRAGMENTS = ("/home/", "/Users/", "\\Users\\")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> ObjectDict:
    path = Path(__file__).with_name("fixtures") / "harness_schema_context.json"
    return object_dict(json.loads(path.read_text(encoding="utf-8")))


def _mapping(data: ObjectDict, key: str) -> ObjectDict:
    return object_dict(data.get(key))


def _string_set(value: object) -> set[str]:
    items = object_list(value)
    return {item for item in items if isinstance(item, str)}


def _source(data: ObjectDict, source_id: str) -> ObjectDict:
    return object_dict(_mapping(data, "sources").get(source_id))


def finding() -> RuleFinding:
    return RuleFinding(
        rule_id="SCHEMA-001",
        title="schema contract",
        severity=Severity.HIGH,
        message="schema contract violation",
        decision="deny",
    )


def test_harness_schema_context_sources_are_official_available_and_parsable() -> None:
    data = _fixture()
    fixture_summary = {
        "schema_version": data["schema_version"],
        "source_snapshot_policy": data["source_snapshot_policy"],
        "errors": data["errors"],
        "sources": set(_mapping(data, "sources").keys()),
    }
    assert fixture_summary == {
        "schema_version": 1,
        "source_snapshot_policy": "manual-regeneration-required",
        "errors": {},
        "sources": set(REQUIRED_SOURCES),
    }

    for source_id, (harness, kind) in REQUIRED_SOURCES.items():
        assert_official_source(source_id, _source(data, source_id), harness, kind)


def test_checked_in_fixture_omits_machine_local_cache_paths() -> None:
    data = _fixture()
    assert "cache_dir" not in data
    sources = _mapping(data, "sources")
    sources_with_cache_paths = [
        source_id
        for source_id, source in sources.items()
        if isinstance(source, dict) and "cache_path" in source
    ]
    assert sources_with_cache_paths == []

    fixture_strings = strings(data)
    leaked = [
        text
        for text in fixture_strings
        if any(part in text for part in LOCAL_PATH_FRAGMENTS)
    ]
    assert leaked == []


def test_opencode_schema_summary_contains_relevant_permission_contract_defs() -> None:
    assert opencode_schema_summary_observed(
        _fixture(),
        expected_defs=EXPECTED_OPENCODE_SCHEMA_DEFS,
    ) == {
        "schema": "https://json-schema.org/draft/2020-12/schema",
        "ref": "#/$defs/Config",
        "has_root_keys": True,
        "has_permission_defs": True,
    }


def _expected_contract_note_flags(cross_check: ObjectDict) -> dict[str, bool]:
    notes = _mapping(cross_check, "notes")
    return {
        "claude_has_richest": "Richest direct hook surface" in str(notes.get("claude")),
        "codex_has_partial": "Partial hooks" in str(notes.get("codex")),
        "opencode_has_plugin": "Plugin-mediated" in str(notes.get("opencode")),
    }


def test_expected_contract_is_human_authored_and_source_cross_checked() -> None:
    cross_check = expected_contract_cross_check(_fixture())
    expected_contract = _mapping(_fixture(), "expected_contract")
    assert {
        "authorities": cross_check["authorities"],
        "missing_source_ids": cross_check["missing_source_ids"],
        "unknown_source_ids": cross_check["unknown_source_ids"],
        **_expected_contract_note_flags(cross_check),
    } == {
        "authorities": {
            harness: "human-authored-source-cross-checked"
            for harness in expected_contract
        },
        "missing_source_ids": [],
        "unknown_source_ids": {harness: [] for harness in expected_contract},
        "claude_has_richest": True,
        "codex_has_partial": True,
        "opencode_has_plugin": True,
    }


def test_fixture_installed_source_paths_exist_and_symbols_are_extractable() -> None:
    data = _fixture()
    installed_sources: list[ObjectDict] = []
    for surface in _mapping(data, "harness_event_surfaces").values():
        if not is_object_dict(surface):
            continue
        installed_source = surface.get("installed_source")
        if is_object_dict(installed_source):
            installed_sources.append(installed_source)
    assert installed_sources, "fixture should record local installer provenance"

    assert_installed_sources_are_extractable(REPO_ROOT, installed_sources)


def test_source_specific_doc_keywords_support_key_contract_claims() -> None:
    data = _fixture()
    source_keyword_hits = _mapping(data, "source_keyword_hits")
    missing_keywords = {
        source_id: sorted(
            required_keywords - _string_set(source_keyword_hits.get(source_id))
        )
        for source_id, required_keywords in REQUIRED_SOURCE_KEYWORDS.items()
    }

    assert missing_keywords == {source_id: [] for source_id in REQUIRED_SOURCE_KEYWORDS}


def test_schema_contract_harnesses_match_registered_adapters() -> None:
    data = _fixture()
    assert set(_mapping(data, "expected_contract").keys()) <= set(ADAPTERS)


def _assert_claude_event_surface_matches_contract(data: ObjectDict) -> None:
    claude_surface = _mapping(_mapping(data, "harness_event_surfaces"), "claude")
    expected_contract = _mapping(data, "expected_contract")

    official_events = _string_set(claude_surface.get("official_events"))
    installed_events = _string_set(claude_surface.get("slopgate_installed_events"))
    intentionally_not_installed = _string_set(
        claude_surface.get("intentionally_not_installed_events")
    )

    assert official_events == EXPECTED_CLAUDE_OFFICIAL_EVENTS
    assert installed_events == set(CLAUDE_EVENTS)
    assert installed_events < official_events
    assert intentionally_not_installed == official_events - installed_events
    claude_contract = _mapping(expected_contract, "claude")
    assert _string_set(claude_contract.get("native_events")) == installed_events
    assert (
        claude_surface.get("coverage_decision")
        == "install-supported-subset-not-full-official-surface"
    )
    assert claude_surface.get("authority") == "official-docs-plus-local-installer"
    assert claude_surface.get("extraction_method") == "claude-hooks-table"
    assert claude_surface.get("unknown_official_events") == []
    assert claude_surface.get("installed_source") == {
        "path": "src/slopgate/installer/_claude.py",
        "symbol": "CLAUDE_EVENTS",
        "load_method": "ast-literal",
    }


def test_claude_official_event_surface_is_recorded_separately_from_installed_subset() -> (
    None
):
    data = _fixture()
    _assert_claude_event_surface_matches_contract(data)
    assert "claude" in _mapping(data, "harness_event_surfaces")


def test_schema_contract_event_maps_match_adapter_normalization() -> None:
    contract_summary = schema_event_map_contract_summary(
        _fixture(),
        opencode_event_map=OPENCODE_EVENT_MAP,
        codex_events=CODEX_EVENTS,
    )
    assert {
        "opencode_native": contract_summary["opencode_native"],
        "opencode_canonical": contract_summary["opencode_canonical"],
        "codex_native": contract_summary["codex_native"],
        "opencode_differs_from_claude": contract_summary[
            "opencode_differs_from_claude"
        ],
    } == {
        "opencode_native": set(OPENCODE_EVENT_MAP),
        "opencode_canonical": set(OPENCODE_EVENT_MAP.values()),
        "codex_native": CODEX_EVENTS,
        "opencode_differs_from_claude": True,
    }

    adapter = OpenCodeAdapter()
    normalized_events = {
        native_event: adapter.normalize_payload({"hook_event_name": native_event})[
            "hook_event_name"
        ]
        for native_event in OPENCODE_EVENT_MAP
    }

    assert normalized_events == OPENCODE_EVENT_MAP


def test_schema_contract_pretool_output_shapes_are_harness_specific() -> None:
    assert pretool_output_summary(finding()) == {
        "claude": {"event": "PreToolUse", "decision": "deny", "has_action": False},
        "codex": {
            "event": "PreToolUse",
            "decision": "deny",
            "has_updated_input": False,
        },
        "opencode": {"action": "block", "has_hook_specific": False},
    }


def test_schema_contract_permission_request_output_shapes_are_harness_specific() -> (
    None
):
    assert permission_request_output_summary(finding()) == {
        "claude": {"behavior": "deny", "has_message": True},
        "codex": {"behavior": "deny", "has_message": True, "has_updated_input": False},
        "opencode": {"action": "block", "has_hook_specific": False},
    }


def test_opencode_stop_output_is_degraded_advisory_not_claude_style_blocking() -> None:
    summary = opencode_stop_output_summary(OpenCodeAdapter(), finding())
    assert summary == {
        "normalized_event": "Stop",
        "is_present": True,
        "action": "continue",
        "has_reason": True,
        "has_hook_specific": False,
    }
