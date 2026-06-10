"""Helpers for harness schema context contract tests."""

from __future__ import annotations

import ast
import importlib
import types
from pathlib import Path
from typing import cast

from slopgate._types import ObjectDict, is_object_dict, object_dict, object_list, string_value
from slopgate.adapters.base import PlatformAdapter
from slopgate.adapters.claude import ClaudeAdapter
from slopgate.adapters.codex import CodexAdapter
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.models import RuleFinding


def module_name_for_source_path(source_path: str) -> str:
    assert source_path.startswith("src/") and source_path.endswith(".py"), source_path
    return source_path.removeprefix("src/").removesuffix(".py").replace("/", ".")


def ast_sequence_values(
    source_path: Path, module: types.ModuleType, symbol: str
) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == symbol
            for target in node.targets
        ):
            continue
        assert isinstance(node.value, (ast.Tuple, ast.List)), symbol
        values: list[str] = []
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            elif isinstance(item, ast.Name) and isinstance(
                getattr(module, item.id, None), str
            ):
                values.append(getattr(module, item.id))
            else:  # pragma: no cover - assertion message carries unexpected AST shape
                raise AssertionError(
                    f"{symbol} contains non-extractable AST node: {ast.dump(item)}"
                )
        return values
    raise AssertionError(f"{symbol} not found in {source_path}")


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if is_object_dict(value):
        return [item for nested in value.values() for item in strings(nested)]
    if isinstance(value, list):
        sequence: list[object] = object_list(cast(object, value))
        return [item for nested in sequence for item in strings(nested)]
    return []


def assert_official_source(
    source_id: str, source: ObjectDict, harness: str, kind: str
) -> None:
    assert source["harness"] == harness
    assert source["kind"] == kind
    assert source["status_code"] == 200
    assert string_value(source.get("content_type"))
    content_type = string_value(source.get("content_type")) or ""
    assert "text/html" not in content_type.lower(), source_id
    url = string_value(source.get("url")) or ""
    assert url.startswith(
        (
            "https://docs.anthropic.com/",
            "https://opencode.ai/",
            "https://developers.openai.com/",
        )
    ), source_id
    sha256 = string_value(source.get("sha256")) or ""
    assert len(sha256) == 64, source_id
    bytes_value = source.get("bytes")
    assert isinstance(bytes_value, int) and bytes_value > 1000, source_id
    retrieved_at = string_value(source.get("retrieved_at_utc")) or ""
    assert retrieved_at.endswith("+00:00"), source_id


def assert_installed_sources_are_extractable(
    repo_root: Path, installed_sources: list[ObjectDict]
) -> None:
    extracted_values_by_path: dict[str, list[str]] = {}
    for source in installed_sources:
        source_path = repo_root / str(source["path"])
        assert source_path.is_file(), source
        module = importlib.import_module(
            module_name_for_source_path(str(source["path"]))
        )
        imported = getattr(module, str(source["symbol"]))
        assert source["load_method"] == "ast-literal"
        extracted_values_by_path[str(source["path"])] = ast_sequence_values(
            source_path, module, str(source["symbol"])
        )
        assert extracted_values_by_path[str(source["path"])] == list(imported)


def mapping(data: ObjectDict, key: str) -> ObjectDict:
    return object_dict(data.get(key))


def string_set(value: object) -> set[str]:
    items = object_list(value)
    return {item for item in items if isinstance(item, str)}


def opencode_schema_summary_observed(
    data: ObjectDict,
    *,
    expected_defs: set[str],
) -> dict[str, object]:
    schema_summary = mapping(
        mapping(mapping(data, "sources"), "opencode_config_schema"),
        "schema_summary",
    )
    root_keys = string_set(schema_summary.get("root_keys"))
    defs_keys = string_set(schema_summary.get("defs_keys"))
    return {
        "schema": schema_summary.get("schema"),
        "ref": schema_summary.get("ref"),
        "has_root_keys": {"$schema", "$ref", "$defs"} <= root_keys,
        "has_permission_defs": expected_defs <= defs_keys,
    }


def expected_contract_cross_check(data: ObjectDict) -> dict[str, object]:
    basis = mapping(data, "contract_basis")
    expected_contract = mapping(data, "expected_contract")
    harness_basis = {
        harness: object_dict(basis.get(harness)) for harness in expected_contract
    }
    authorities = {
        harness: string_value(contract_basis.get("authority"))
        for harness, contract_basis in harness_basis.items()
    }
    source_ids = {
        harness: string_set(contract_basis.get("source_ids"))
        for harness, contract_basis in harness_basis.items()
    }
    missing_source_ids = [harness for harness, ids in source_ids.items() if not ids]
    unknown_source_ids = {
        harness: [
            source_id for source_id in ids if source_id not in mapping(data, "sources")
        ]
        for harness, ids in source_ids.items()
    }
    notes = {
        harness: string_value(object_dict(contract).get("blocking_notes")) or ""
        for harness, contract in expected_contract.items()
    }
    return {
        "authorities": authorities,
        "missing_source_ids": missing_source_ids,
        "unknown_source_ids": unknown_source_ids,
        "notes": notes,
    }


def schema_event_map_contract_summary(
    data: ObjectDict,
    *,
    opencode_event_map: dict[str, str],
    codex_events: set[str],
) -> dict[str, object]:
    contracts = mapping(data, "expected_contract")
    opencode_contract = mapping(contracts, "opencode")
    codex_contract = mapping(contracts, "codex")
    claude_contract = mapping(contracts, "claude")
    return {
        "opencode_native": string_set(opencode_contract.get("native_events")),
        "opencode_canonical": string_set(opencode_contract.get("canonical_events")),
        "codex_native": string_set(codex_contract.get("native_events")),
        "opencode_differs_from_claude": opencode_contract.get("native_events")
        != claude_contract.get("native_events"),
        "opencode_event_map": opencode_event_map,
        "codex_events": codex_events,
    }


def hook_specific(output: ObjectDict) -> ObjectDict:
    specific = output.get("hookSpecificOutput")
    assert is_object_dict(specific), output
    return specific


def render_denied_output(
    adapter: PlatformAdapter,
    event_name: str,
    finding: RuleFinding,
) -> ObjectDict:
    output = adapter.render_output(event_name, [finding], decision="deny")
    assert output is not None
    return object_dict(output)


def permission_decision_summary(decision: ObjectDict) -> dict[str, object]:
    return {
        "behavior": decision.get("behavior"),
        "has_message": "message" in decision,
    }


def pretool_output_summary(finding: RuleFinding) -> dict[str, dict[str, object]]:
    claude_output = render_denied_output(ClaudeAdapter(), "PreToolUse", finding)
    codex_output = render_denied_output(CodexAdapter(), "PreToolUse", finding)
    opencode_output = render_denied_output(OpenCodeAdapter(), "PreToolUse", finding)
    return {
        "claude": {
            "event": string_value(hook_specific(claude_output).get("hookEventName")),
            "decision": string_value(
                hook_specific(claude_output).get("permissionDecision")
            ),
            "has_action": "action" in claude_output,
        },
        "codex": {
            "event": string_value(hook_specific(codex_output).get("hookEventName")),
            "decision": string_value(
                hook_specific(codex_output).get("permissionDecision")
            ),
            "has_updated_input": "updatedInput" in hook_specific(codex_output),
        },
        "opencode": {
            "action": string_value(opencode_output.get("action")),
            "has_hook_specific": "hookSpecificOutput" in opencode_output,
        },
    }


def permission_request_output_summary(
    finding: RuleFinding,
) -> dict[str, dict[str, object]]:
    claude_output = render_denied_output(ClaudeAdapter(), "PermissionRequest", finding)
    codex_output = render_denied_output(CodexAdapter(), "PermissionRequest", finding)
    opencode_output = render_denied_output(
        OpenCodeAdapter(), "PermissionRequest", finding
    )
    return {
        "claude": permission_decision_summary(
            object_dict(hook_specific(claude_output).get("decision"))
        ),
        "codex": permission_decision_summary(
            object_dict(hook_specific(codex_output).get("decision"))
        )
        | {
            "has_updated_input": "updatedInput"
            in object_dict(hook_specific(codex_output).get("decision"))
        },
        "opencode": {
            "action": string_value(opencode_output.get("action")),
            "has_hook_specific": "hookSpecificOutput" in opencode_output,
        },
    }


def opencode_stop_output_summary(adapter: object, finding: object) -> dict[str, object]:
    normalize = getattr(adapter, "normalize_payload")
    render_output = getattr(adapter, "render_output")
    payload = normalize({"hook_event_name": "session.idle"})
    output = render_output("Stop", [finding], decision="deny")
    return {
        "normalized_event": payload["hook_event_name"],
        "is_present": output is not None,
        "action": output["action"] if output else None,
        "has_reason": bool(output and "reason" in output),
        "has_hook_specific": bool(output and "hookSpecificOutput" in output),
    }
