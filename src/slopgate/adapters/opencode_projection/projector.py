"""Filesystem-aware OpenCode mutation projection orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from slopgate._types import ObjectDict, ObjectMapping, object_dict, object_list, string_value
from slopgate.constants import DENY, METADATA_CONTENT, METADATA_PATH, PRE_TOOL_USE
from slopgate.models import RuleFinding, Severity
from slopgate.opencode_tool_capabilities import (
    OpenCodeToolCapability,
    opencode_tool_capability,
)
from slopgate.util.payloads import is_read_only_tool_use, is_shell_tool
from .models import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    PROJECTION_KEY,
    PatchSection,
    ProjectedFile,
    Projection,
    ProjectionRequest,
    Snapshot,
    SnapshotStatus,
)
from .patch import apply_update, parse_patch
from .snapshot import read_snapshot


@dataclass(frozen=True, slots=True)
class _SectionSource:
    content: str
    sha256: str | None


def _target(root: Path, value: str) -> tuple[Path, str] | None:
    if not value.strip():
        return None
    root = root.resolve()
    candidate = Path(value)
    raw_path = candidate if candidate.is_absolute() else root / candidate
    path = Path(os.path.abspath(raw_path))
    if not path.is_relative_to(root):
        return None
    return path, path.relative_to(root).as_posix()


def _request_target(request: ProjectionRequest) -> tuple[Path, str] | None:
    raw_path = string_value(request.tool_input.get("filePath")) or ""
    return _target(request.root, raw_path)


def _snapshot_digest(root: Path, relative: str) -> str | None | SnapshotStatus:
    snapshot = read_snapshot(root, relative)
    if isinstance(snapshot, Snapshot):
        return snapshot.sha256
    if snapshot == "missing":
        return None
    return snapshot


def _project_write(request: ProjectionRequest) -> Projection:
    target = _request_target(request)
    content = string_value(request.tool_input.get(METADATA_CONTENT))
    if target is None or content is None:
        return Projection("invalid")
    _path, relative = target
    digest = _snapshot_digest(request.root, relative)
    if digest == "invalid" or digest == "stale":
        return Projection(digest)
    return Projection(
        "projected",
        (ProjectedFile(relative, content, "write", digest),),
    )


def _project_edit(request: ProjectionRequest) -> Projection:
    target = _request_target(request)
    old = string_value(request.tool_input.get("oldString"))
    new = string_value(request.tool_input.get("newString"))
    if target is None or not old or new is None:
        return Projection("invalid")
    _path, relative = target
    snapshot = read_snapshot(request.root, relative)
    if not isinstance(snapshot, Snapshot):
        return Projection("invalid" if snapshot == "missing" else snapshot)
    count = snapshot.content.count(old)
    replace_all = request.tool_input.get("replaceAll") is True
    if count == 0 or (not replace_all and count != 1):
        return Projection("invalid")
    content = snapshot.content.replace(old, new, -1 if replace_all else 1)
    return Projection(
        "projected",
        (ProjectedFile(relative, content, "edit", snapshot.sha256),),
    )


def _section_source(
    root: Path,
    section: PatchSection,
) -> _SectionSource | SnapshotStatus:
    target = _target(root, section.path)
    if target is None:
        return "invalid"
    _path, relative = target
    snapshot = read_snapshot(root, relative)
    if isinstance(snapshot, Snapshot):
        if section.operation == "add":
            return "invalid"
        return _SectionSource(snapshot.content, snapshot.sha256)
    if snapshot == "missing":
        return _SectionSource("", None) if section.operation == "add" else "invalid"
    return snapshot


def _section_content(
    section: PatchSection,
    source: str,
) -> str | None:
    match section.operation:
        case "add":
            valid_add = all(line.startswith("+") for line in section.lines)
            if not valid_add:
                return None
            return "\n".join(line[1:] for line in section.lines) + "\n"
        case "update":
            return apply_update(source, section.lines)
        case "delete":
            return "" if not section.lines else None
    return None


def _project_patch(request: ProjectionRequest) -> Projection:
    patch_text = string_value(request.tool_input.get("patchText")) or ""
    sections = parse_patch(patch_text)
    if sections is None:
        return Projection("invalid")
    files: dict[str, ProjectedFile] = {}
    for section in sections:
        target = _target(request.root, section.path)
        if target is None:
            return Projection("invalid")
        _path, relative = target
        if relative in files:
            return Projection("invalid")
        resolved = _section_source(request.root, section)
        if not isinstance(resolved, _SectionSource):
            return Projection("invalid" if resolved == "missing" else resolved)
        content = _section_content(section, resolved.content)
        if content is None:
            return Projection("invalid")
        files[relative] = ProjectedFile(
            relative,
            content,
            section.operation,
            resolved.sha256,
        )
    return Projection("projected", tuple(files.values()))


_UNRESOLVED_PROJECTION_MESSAGES = {
    "invalid": "OpenCode mutation projection is invalid; refusing execution.",
    "stale": "OpenCode mutation projection is stale; refusing execution.",
    "protocol_mismatch": (
        "OpenCode tool contract mismatch; refusing unresolved mutation."
    ),
    "unsupported": "Unknown OpenCode tool effect; denying by default.",
}


def unresolved_opencode_projection_finding(
    tool_name: str,
    tool_input: ObjectMapping,
    event_name: str,
) -> RuleFinding | None:
    """Return a deny finding when an OpenCode mutation cannot be projected safely."""
    if event_name != PRE_TOOL_USE:
        return None
    projection = object_dict(tool_input.get(PROJECTION_KEY))
    status = string_value(projection.get("status")) or ""
    if status == "projected":
        return None
    capability = opencode_tool_capability(tool_name)
    if (
        is_read_only_tool_use({"tool_name": tool_name, "hook_event_name": event_name})
        or is_shell_tool(tool_name)
        or capability is OpenCodeToolCapability.READ_ONLY
        or (
            status == "unsupported"
            and capability is OpenCodeToolCapability.EFFECTFUL
        )
    ):
        return None
    return RuleFinding(
        rule_id="OC-PROJECTION-001",
        title="Unresolved OpenCode mutation projection",
        severity=Severity.CRITICAL,
        decision=DENY,
        message=_UNRESOLVED_PROJECTION_MESSAGES.get(
            status,
            "Unresolved OpenCode mutation projection; refusing execution.",
        ),
        metadata={"projection_status": status or "missing"},
    )


def project_opencode_tool_input(request: ProjectionRequest) -> ObjectDict:
    """Return projection metadata without mutating arguments or files."""
    if request.contract_version != OPENCODE_TOOL_CONTRACT_VERSION:
        return Projection("protocol_mismatch").to_dict()
    match request.tool_name.strip().lower():
        case "write":
            result = _project_write(request)
        case "edit":
            result = _project_edit(request)
        case "apply_patch":
            result = _project_patch(request)
        case _:
            result = Projection("unsupported")
    return result.to_dict()


def normalize_projected_tool_input(request: ProjectionRequest) -> ObjectDict:
    """Return canonical analysis input containing complete projected edits."""
    projection = project_opencode_tool_input(request)
    enriched_input = dict(request.tool_input)
    enriched_input[PROJECTION_KEY] = projection
    if projection.get("status") != "projected":
        return enriched_input
    projected_edits: list[ObjectDict] = []
    for value in object_list(projection.get("files")):
        item = object_dict(value)
        edit: ObjectDict = {"file_path": item.get(METADATA_PATH, "")}
        if item.get("operation") == "delete":
            edit["operation"] = "delete"
        else:
            edit[METADATA_CONTENT] = item.get(METADATA_CONTENT, "")
        projected_edits.append(edit)
    enriched_input["edits"] = projected_edits
    if request.tool_name.strip().lower() == "apply_patch":
        patch_text = enriched_input.pop("patchText", "")
        enriched_input["_slopgate_original_patch_text"] = patch_text
    return enriched_input
