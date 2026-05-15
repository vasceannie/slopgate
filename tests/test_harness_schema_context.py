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

from vibeforcer.adapters import ADAPTERS
from vibeforcer.adapters.claude import ClaudeAdapter
from vibeforcer.adapters.codex import CODEX_EVENTS, CodexAdapter
from vibeforcer.adapters.opencode import OPENCODE_EVENT_MAP, OpenCodeAdapter
from vibeforcer.installer import _CLAUDE_EVENTS
from vibeforcer.models import RuleFinding, Severity

EXPECTED_CLAUDE_OFFICIAL_EVENTS = {
    "SessionStart",
    "Setup",
    "CwdChanged",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PreToolUse",
    "PermissionRequest",
    "PermissionDenied",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Elicitation",
    "ElicitationResult",
    "InstructionsLoaded",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "Notification",
    "FileChanged",
}

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


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _strings(nested)]
    return []


def test_harness_schema_context_sources_are_official_available_and_parsable() -> None:
    data = _fixture()
    assert data["schema_version"] == 1
    assert data["source_snapshot_policy"] == "manual-regeneration-required"
    assert data["errors"] == {}
    assert set(data["sources"]) == set(REQUIRED_SOURCES)

    for source_id, (harness, kind) in REQUIRED_SOURCES.items():
        source = data["sources"][source_id]
        assert source["harness"] == harness
        assert source["kind"] == kind
        assert source["status_code"] == 200
        assert source["content_type"]
        assert "text/html" not in source["content_type"].lower(), source_id
        assert source["url"].startswith((
            "https://docs.anthropic.com/",
            "https://opencode.ai/",
            "https://developers.openai.com/",
        )), source_id
        assert len(source["sha256"]) == 64, source_id
        assert source["bytes"] > 1000, source_id
        assert source["retrieved_at_utc"].endswith("+00:00"), source_id


def test_checked_in_fixture_omits_machine_local_cache_paths() -> None:
    data = _fixture()
    assert "cache_dir" not in data
    for source_id, source in data["sources"].items():
        assert "cache_path" not in source, source_id

    strings = _strings(data)
    leaked = [text for text in strings if any(part in text for part in LOCAL_PATH_FRAGMENTS)]
    assert leaked == []


def test_opencode_schema_summary_contains_relevant_permission_contract_defs() -> None:
    data = _fixture()
    schema_summary = data["sources"]["opencode_config_schema"]["schema_summary"]
    assert schema_summary["schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema_summary["ref"] == "#/$defs/Config"
    assert {"$schema", "$ref", "$defs"} <= set(schema_summary["root_keys"])
    assert EXPECTED_OPENCODE_SCHEMA_DEFS <= set(schema_summary["defs_keys"])


def test_expected_contract_is_human_authored_and_source_cross_checked() -> None:
    data = _fixture()
    basis = data["contract_basis"]
    for harness in data["expected_contract"]:
        harness_basis = basis[harness]
        assert harness_basis["authority"] == "human-authored-source-cross-checked"
        assert harness_basis["source_ids"]
        for source_id in harness_basis["source_ids"]:
            assert source_id in data["sources"]


def test_source_specific_doc_keywords_support_key_contract_claims() -> None:
    data = _fixture()
    source_keyword_hits = data["source_keyword_hits"]
    for source_id, required_keywords in REQUIRED_SOURCE_KEYWORDS.items():
        observed = set(source_keyword_hits[source_id])
        assert required_keywords <= observed, (source_id, required_keywords - observed)


def test_schema_contract_harnesses_match_registered_adapters() -> None:
    data = _fixture()
    assert set(data["expected_contract"]) <= set(ADAPTERS)


def test_claude_official_event_surface_is_recorded_separately_from_installed_subset() -> None:
    data = _fixture()
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
        "path": "src/vibeforcer/installer.py",
        "symbol": "_CLAUDE_EVENTS",
        "load_method": "ast-literal",
    }


def test_schema_contract_event_maps_match_adapter_normalization() -> None:
    data = _fixture()
    contracts = data["expected_contract"]

    assert set(contracts["opencode"]["native_events"]) == set(OPENCODE_EVENT_MAP)
    assert set(OPENCODE_EVENT_MAP.values()) == set(contracts["opencode"]["canonical_events"])
    assert set(contracts["codex"]["native_events"]) == CODEX_EVENTS
    assert contracts["opencode"]["native_events"] != contracts["claude"]["native_events"]

    adapter = OpenCodeAdapter()
    for native_event, canonical_event in OPENCODE_EVENT_MAP.items():
        payload = adapter.normalize_payload({"hook_event_name": native_event})
        assert payload["hook_event_name"] == canonical_event


def test_schema_contract_pretool_output_shapes_are_harness_specific() -> None:
    finding = _finding()

    claude_output = ClaudeAdapter().render_output(
        "PreToolUse", [finding], decision="deny"
    )
    assert claude_output is not None
    claude_specific = _hook_specific(claude_output)
    assert claude_specific["hookEventName"] == "PreToolUse"
    assert claude_specific["permissionDecision"] == "deny"
    assert "action" not in claude_output

    codex_output = CodexAdapter().render_output("PreToolUse", [finding], decision="deny")
    assert codex_output is not None
    codex_specific = _hook_specific(codex_output)
    assert codex_specific["hookEventName"] == "PreToolUse"
    assert codex_specific["permissionDecision"] == "deny"
    assert "updatedInput" not in codex_specific

    opencode_output = OpenCodeAdapter().render_output(
        "PreToolUse", [finding], decision="deny"
    )
    assert opencode_output is not None
    assert opencode_output["action"] == "block"
    assert "hookSpecificOutput" not in opencode_output


def test_schema_contract_permission_request_output_shapes_are_harness_specific() -> None:
    finding = _finding()

    claude_output = ClaudeAdapter().render_output(
        "PermissionRequest", [finding], decision="deny"
    )
    assert claude_output is not None
    claude_decision = _hook_specific(claude_output)["decision"]
    assert claude_decision["behavior"] == "deny"
    assert "message" in claude_decision

    codex_output = CodexAdapter().render_output(
        "PermissionRequest", [finding], decision="deny"
    )
    assert codex_output is not None
    codex_decision = _hook_specific(codex_output)["decision"]
    assert codex_decision["behavior"] == "deny"
    assert "message" in codex_decision
    assert "updatedInput" not in codex_decision

    opencode_output = OpenCodeAdapter().render_output(
        "PermissionRequest", [finding], decision="deny"
    )
    assert opencode_output is not None
    assert opencode_output["action"] == "block"
    assert "hookSpecificOutput" not in opencode_output


def test_opencode_stop_output_is_degraded_advisory_not_claude_style_blocking() -> None:
    adapter = OpenCodeAdapter()
    payload = adapter.normalize_payload({"hook_event_name": "session.idle"})
    assert payload["hook_event_name"] == "Stop"

    output = adapter.render_output("Stop", [_finding()], decision="deny")
    assert output is not None
    assert output["action"] == "continue"
    assert "reason" in output
    assert "hookSpecificOutput" not in output
    assert output["action"] != "block"
