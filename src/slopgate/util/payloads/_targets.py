from __future__ import annotations

from collections.abc import Iterable

from slopgate._types import ObjectMapping, object_dict, object_list
from slopgate.models import ContentTarget

from ._basic import extract_content_from_mapping, extract_path_from_mapping, first_present
from ._patches import extract_added_patch_content, parse_patch_candidate_paths

def _tool_input_path(tool_input: ObjectMapping, payload: ObjectMapping) -> str:
    merged = dict(tool_input)
    _ = merged.setdefault("resolved_file_path", payload.get("resolved_file_path"))
    _ = merged.setdefault("original_file_path", payload.get("original_file_path"))
    return extract_path_from_mapping(merged)


def _tool_input_content_target(
    tool_input: ObjectMapping, path_value: str
) -> ContentTarget | None:
    content_value = extract_content_from_mapping(tool_input)
    if not path_value or not content_value:
        return None
    return ContentTarget(path=path_value, content=content_value, source="tool_input")


def _multi_edit_content_targets(
    tool_input: ObjectMapping, fallback_path: str
) -> list[ContentTarget]:
    targets: list[ContentTarget] = []
    for item in object_list(tool_input.get("edits")):
        item_dict = object_dict(item)
        if not item_dict:
            continue
        path_item = extract_path_from_mapping(item_dict) or fallback_path
        content_item = extract_content_from_mapping(item_dict)
        if path_item and content_item:
            targets.append(
                ContentTarget(path=path_item, content=content_item, source="multi_edit")
            )
            continue
        old_text = first_present(item_dict, ("oldText", "old_text"), strip=False)
        if path_item and old_text:
            targets.append(
                ContentTarget(path=path_item, content=old_text, source="multi_edit_old")
            )
    return targets


def _patch_content_targets(tool_input: ObjectMapping) -> list[ContentTarget]:
    patch_blob = first_present(tool_input, ("patch", "patchText", "patch_text"))
    if not patch_blob:
        return []
    patch_content = extract_added_patch_content(patch_blob) or patch_blob
    return [
        ContentTarget(path=path_item, content=patch_content, source="patch")
        for path_item in parse_patch_candidate_paths(patch_blob) or ["patch.diff"]
    ]


def _unique_content_targets(targets: list[ContentTarget]) -> list[ContentTarget]:
    unique_by_key: dict[tuple[str, str, str], ContentTarget] = {}
    for target in targets:
        key = (target.path, target.content, target.source)
        _ = unique_by_key.setdefault(key, target)
    return list(unique_by_key.values())


def _append_candidate_path(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _direct_candidate_paths(
    payload: ObjectMapping, tool_input: ObjectMapping
) -> list[str]:
    values: list[str] = []
    for source in (payload, tool_input):
        _append_candidate_path(values, extract_path_from_mapping(source))
    return values


def _multi_edit_candidate_paths(tool_input: ObjectMapping) -> list[str]:
    values: list[str] = []
    for item in object_list(tool_input.get("edits")):
        path_item = extract_path_from_mapping(object_dict(item))
        _append_candidate_path(values, path_item)
    return values


def _patch_candidate_paths(tool_input: ObjectMapping) -> list[str]:
    patch_blob = first_present(tool_input, ("patch", "patchText", "patch_text"))
    return parse_patch_candidate_paths(patch_blob) if patch_blob else []


def _tool_response_candidate_paths(payload: ObjectMapping) -> list[str]:
    path_value = extract_path_from_mapping(object_dict(payload.get("tool_response")))
    return [path_value] if path_value else []


def _unique_paths(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        _append_candidate_path(result, item)
    return result
