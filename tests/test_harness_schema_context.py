"""Doc-derived schema/context contract for harness docs used by Vibeforcer tests.

Regenerate with:
python3 <skill>/scripts/harness_schema_context.py --write-tests --format markdown

These tests bind a generated fixture to official-source metadata, source-specific
doc evidence, and Vibeforcer's adapter contracts. They are not a replacement for
focused behavior tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.harness_schema_support import (
    assert_installed_sources_are_extractable,
    assert_official_source,
    strings,
)
from vibeforcer.adapters import ADAPTERS
from vibeforcer.adapters.claude import ClaudeAdapter
from vibeforcer.adapters.codex import CODEX_EVENTS, CodexAdapter
from vibeforcer.adapters.opencode import OPENCODE_EVENT_MAP, OpenCodeAdapter
from vibeforcer.installer import _CLAUDE_EVENTS
from vibeforcer.models import RuleFinding, Severity

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
    "opencode_plugin_docs": {"tool.execute.before", "tool.execute.after", "permission.asked", "session.idle"},
    "codex_hooks": {"codex_hooks", "PreToolUse", "PermissionRequest"},
}

EXPECTED_OPENCODE_SCHEMA_DEFS = {"Config", "PermissionActionConfig", "PermissionConfig", "PermissionRuleConfig"}

LOCAL_PATH_FRAGMENTS = ("/home/", "/Users/", "\\Users\\")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> dict[str, Any]:
    path = Path(__file__).with_name("fixtures") / "harness_schema_context.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _finding() -> RuleFinding:
    return RuleFinding(
        rule_id="SCHEMA-001",
        title="schema contract",
        severity=Severity.HIGH,
        message="schema contract violation",
        decision="deny",
    )


def _hook_specific(output: dict[str, Any]) -> dict[str, Any]:
    specific = output.get("hookSpecificOutput")
    assert isinstance(specific, dict), output
    return specific


def _render_denied_output(adapter: Any, event_name: str, finding: RuleFinding) -> dict[str, Any]:
    output = adapter.render_output(event_name, [finding], decision="deny")
    assert output is not None
    return output


def test_harness_schema_context_sources_are_official_available_and_parsable() -> None:
    data = _fixture()
    fixture_summary = {
        "schema_version": data["schema_version"],
        "source_snapshot_policy": data["source_snapshot_policy"],
        "errors": data["errors"],
        "sources": set(data["sources"]),
    }
    assert fixture_summary == {
        "schema_version": 1,
        "source_snapshot_policy": "manual-regeneration-required",
        "errors": {},
        "sources": set(REQUIRED_SOURCES),
    }

    for source_id, (harness, kind) in REQUIRED_SOURCES.items():
        source = data["sources"][source_id]
        assert_official_source(source_id, source, harness, kind)


def test_checked_in_fixture_omits_machine_local_cache_paths() -> None:
    data = _fixture()
    assert "cache_dir" not in data
    sources_with_cache_paths = [
        source_id for source_id, source in data["sources"].items() if "cache_path" in source
    ]
    assert sources_with_cache_paths == []

    fixture_strings = strings(data)
    leaked = [text for text in fixture_strings if any(part in text for part in LOCAL_PATH_FRAGMENTS)]
    assert leaked == []


def test_opencode_schema_summary_contains_relevant_permission_contract_defs() -> None:
    data = _fixture()
    schema_summary = data["sources"]["opencode_config_schema"]["schema_summary"]
    observed = {
        "schema": schema_summary["schema"],
        "ref": schema_summary["ref"],
        "has_root_keys": {"$schema", "$ref", "$defs"} <= set(schema_summary["root_keys"]),
        "has_permission_defs": EXPECTED_OPENCODE_SCHEMA_DEFS <= set(schema_summary["defs_keys"]),
    }
    assert observed == {
        "schema": "https://json-schema.org/draft/2020-12/schema",
        "ref": "#/$defs/Config",
        "has_root_keys": True,
        "has_permission_defs": True,
    }


def test_expected_contract_is_human_authored_and_source_cross_checked() -> None:
    data = _fixture()
    basis = data["contract_basis"]
    harness_basis = {harness: basis[harness] for harness in data["expected_contract"]}
    authorities = {harness: contract_basis["authority"] for harness, contract_basis in harness_basis.items()}
    source_ids = {harness: contract_basis["source_ids"] for harness, contract_basis in harness_basis.items()}
    missing_source_ids = [harness for harness, ids in source_ids.items() if not ids]
    unknown_source_ids = {
        harness: [source_id for source_id in ids if source_id not in data["sources"]]
        for harness, ids in source_ids.items()
    }

    assert authorities == {harness: "human-authored-source-cross-checked" for harness in data["expected_contract"]}
    assert missing_source_ids == []
    assert unknown_source_ids == {harness: [] for harness in data["expected_contract"]}
    notes = {harness: contract["blocking_notes"] for harness, contract in data["expected_contract"].items()}
    assert "Richest direct hook surface" in notes["claude"]
    assert "Partial hooks" in notes["codex"]
    assert "Plugin-mediated" in notes["opencode"]


def test_fixture_installed_source_paths_exist_and_symbols_are_extractable() -> None:
    data = _fixture()
    installed_sources = [
        surface["installed_source"]
        for surface in data["harness_event_surfaces"].values()
        if "installed_source" in surface
    ]
    assert installed_sources, "fixture should record local installer provenance"

    assert_installed_sources_are_extractable(REPO_ROOT, installed_sources)


def test_source_specific_doc_keywords_support_key_contract_claims() -> None:
    data = _fixture()
    source_keyword_hits = data["source_keyword_hits"]
    missing_keywords = {
        source_id: sorted(required_keywords - set(source_keyword_hits[source_id]))
        for source_id, required_keywords in REQUIRED_SOURCE_KEYWORDS.items()
    }

    assert missing_keywords == {source_id: [] for source_id in REQUIRED_SOURCE_KEYWORDS}


def test_schema_contract_harnesses_match_registered_adapters() -> None:
    data = _fixture()
    assert set(data["expected_contract"]) <= set(ADAPTERS)


def _assert_claude_event_surface_matches_contract(data: dict[str, Any]) -> None:
    claude_surface = data["harness_event_surfaces"]["claude"]

    official_events = set(claude_surface["official_events"])
    installed_events = set(claude_surface["vibeforcer_installed_events"])
    intentionally_not_installed = set(claude_surface["intentionally_not_installed_events"])

    assert official_events == EXPECTED_CLAUDE_OFFICIAL_EVENTS
    assert installed_events == set(_CLAUDE_EVENTS)
    assert installed_events < official_events
    assert intentionally_not_installed == official_events - installed_events
    assert set(data["expected_contract"]["claude"]["native_events"]) == installed_events
    assert claude_surface["coverage_decision"] == "install-supported-subset-not-full-official-surface"
    assert claude_surface["authority"] == "official-docs-plus-local-installer"
    assert claude_surface["extraction_method"] == "claude-hooks-table"
    assert claude_surface["unknown_official_events"] == []
    assert claude_surface["installed_source"] == {
        "path": "src/vibeforcer/installer/_claude.py",
        "symbol": "_CLAUDE_EVENTS",
        "load_method": "ast-literal",
    }


def test_claude_official_event_surface_is_recorded_separately_from_installed_subset() -> None:
    data = _fixture()
    _assert_claude_event_surface_matches_contract(data)
    assert "claude" in data["harness_event_surfaces"]


def test_schema_contract_event_maps_match_adapter_normalization() -> None:
    data = _fixture()
    contracts = data["expected_contract"]

    contract_summary = {
        "opencode_native": set(contracts["opencode"]["native_events"]),
        "opencode_canonical": set(contracts["opencode"]["canonical_events"]),
        "codex_native": set(contracts["codex"]["native_events"]),
        "opencode_differs_from_claude": contracts["opencode"]["native_events"]
        != contracts["claude"]["native_events"],
    }
    assert contract_summary == {
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


def _pretool_output_summary(finding: RuleFinding) -> dict[str, dict[str, object]]:
    claude_output = _render_denied_output(ClaudeAdapter(), "PreToolUse", finding)
    codex_output = _render_denied_output(CodexAdapter(), "PreToolUse", finding)
    opencode_output = _render_denied_output(OpenCodeAdapter(), "PreToolUse", finding)
    return {
        "claude": {
            "event": _hook_specific(claude_output)["hookEventName"],
            "decision": _hook_specific(claude_output)["permissionDecision"],
            "has_action": "action" in claude_output,
        },
        "codex": {
            "event": _hook_specific(codex_output)["hookEventName"],
            "decision": _hook_specific(codex_output)["permissionDecision"],
            "has_updated_input": "updatedInput" in _hook_specific(codex_output),
        },
        "opencode": {
            "action": opencode_output["action"],
            "has_hook_specific": "hookSpecificOutput" in opencode_output,
        },
    }


def _permission_request_output_summary(finding: RuleFinding) -> dict[str, dict[str, object]]:
    claude_output = _render_denied_output(ClaudeAdapter(), "PermissionRequest", finding)
    codex_output = _render_denied_output(CodexAdapter(), "PermissionRequest", finding)
    opencode_output = _render_denied_output(OpenCodeAdapter(), "PermissionRequest", finding)
    return {
        "claude": _permission_decision_summary(_hook_specific(claude_output)["decision"]),
        "codex": _permission_decision_summary(_hook_specific(codex_output)["decision"])
        | {"has_updated_input": "updatedInput" in _hook_specific(codex_output)["decision"]},
        "opencode": {
            "action": opencode_output["action"],
            "has_hook_specific": "hookSpecificOutput" in opencode_output,
        },
    }


def _permission_decision_summary(decision: dict[str, Any]) -> dict[str, object]:
    return {"behavior": decision["behavior"], "has_message": "message" in decision}


def test_schema_contract_pretool_output_shapes_are_harness_specific() -> None:
    assert _pretool_output_summary(_finding()) == {
        "claude": {"event": "PreToolUse", "decision": "deny", "has_action": False},
        "codex": {"event": "PreToolUse", "decision": "deny", "has_updated_input": False},
        "opencode": {"action": "block", "has_hook_specific": False},
    }


def test_schema_contract_permission_request_output_shapes_are_harness_specific() -> None:
    assert _permission_request_output_summary(_finding()) == {
        "claude": {"behavior": "deny", "has_message": True},
        "codex": {"behavior": "deny", "has_message": True, "has_updated_input": False},
        "opencode": {"action": "block", "has_hook_specific": False},
    }


def test_opencode_stop_output_is_degraded_advisory_not_claude_style_blocking() -> None:
    adapter = OpenCodeAdapter()
    payload = adapter.normalize_payload({"hook_event_name": "session.idle"})
    assert payload["hook_event_name"] == "Stop"

    output = adapter.render_output("Stop", [_finding()], decision="deny")
    output_summary = {
        "is_present": output is not None,
        "action": output["action"] if output else None,
        "has_reason": bool(output and "reason" in output),
        "has_hook_specific": bool(output and "hookSpecificOutput" in output),
    }
    assert output_summary == {
        "is_present": True,
        "action": "continue",
        "has_reason": True,
        "has_hook_specific": False,
    }
