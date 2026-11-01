"""Filesystem-aware OpenCode mutation projection orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from slopgate._types import (
    ObjectDict,
    ObjectMapping,
    object_dict,
    object_list,
    string_value,
)
from slopgate.constants import DENY, METADATA_CONTENT, METADATA_PATH, PRE_TOOL_USE
from slopgate.config import resolve_repo_root
from slopgate.models import RuleFinding, Severity
from slopgate.opencode_tool_capabilities import (
    OpenCodeToolCapability,
    OPENCODE_PATCH_TOOL_ID,
    native_opencode_mutation_tool_id,
    opencode_tool_capability,
)
from slopgate.util import logger
from .models import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    PROJECTION_KEY,
    PatchSection,
    ProjectedFile,
    Projection,
    ProjectionRequest,
    Snapshot,
    UNRESOLVED_PROJECTION_MESSAGES,
)
from .edit import _project_edit, _request_target, _snapshot_digest, _target
from .patch import invalid_patch_projection, parse_patch, patch_text, section_content
from .snapshot import read_snapshot


@dataclass(frozen=True, slots=True)
class _SectionSource:
    relative: str
    content: str
    sha256: str | None


def _project_write(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode write projection requested", tool=request.tool_name)
    target = _request_target(request)
    content = string_value(request.tool_input.get(METADATA_CONTENT))
    if isinstance(target, Projection):
        return target
    if content is None:
        return Projection("invalid")
    _path, relative = target
    snapshot = read_snapshot(request.root, relative)
    if snapshot != "missing" and not isinstance(snapshot, Snapshot):
        return Projection(snapshot)
    digest = snapshot.sha256 if isinstance(snapshot, Snapshot) else None
    if isinstance(snapshot, Snapshot) and snapshot.content.startswith("\ufeff"):
        content = "\ufeff" + content.removeprefix("\ufeff")
    return Projection(
        "projected",
        (ProjectedFile(relative, content, "write", digest),),
    )


def _section_source(
    request: ProjectionRequest, section: PatchSection, files: dict[str, ProjectedFile]
) -> _SectionSource | Literal["invalid", "stale"] | Projection:
    logger.debug("OpenCode patch source requested", operation=section.operation)
    target = _target(request, section.path)
    if isinstance(target, Projection):
        return target
    _path, relative = target
    previous = files.get(relative)
    if previous is not None:
        if previous.operation == "delete" and section.operation != "add":
            return "invalid"
        return _SectionSource(relative, previous.content, previous.preimage_sha256)
    snapshot = read_snapshot(request.root, relative)
    if isinstance(snapshot, Snapshot):
        return _SectionSource(relative, snapshot.content, snapshot.sha256)
    if snapshot == "missing":
        return (
            _SectionSource(relative, "", None)
            if section.operation == "add"
            else "invalid"
        )
    return snapshot


def _project_move(
    request: ProjectionRequest,
    section: PatchSection,
    resolved: _SectionSource,
    files: dict[str, ProjectedFile],
) -> Projection | None:
    logger.debug("OpenCode move projection requested", path=section.path)
    if section.move_to is None:
        return None
    relative = resolved.relative
    content = section_content(section, resolved.content)
    if content is None:
        return invalid_patch_projection(section.operation, relative)
    destination = _target(request, section.move_to)
    if isinstance(destination, Projection):
        return destination
    _destination_path, destination_relative = destination
    if destination_relative == relative:
        return None
    # Native v2 moves may overwrite a destination; retain its original fingerprint.
    digest = _snapshot_digest(request.root, destination_relative)
    if digest in ("invalid", "stale"):
        return Projection(digest)
    files[relative] = ProjectedFile(relative, "", "delete", resolved.sha256)
    files[destination_relative] = ProjectedFile(
        destination_relative, content, "add", digest
    )
    return Projection("projected", (files[relative], files[destination_relative]))


def _project_patch_section(
    request: ProjectionRequest,
    section: PatchSection,
    files: dict[str, ProjectedFile],
    projected: list[ProjectedFile],
) -> Projection | None:
    logger.debug("OpenCode patch section projection requested", path=section.path)
    resolved = _section_source(request, section, files)
    if isinstance(resolved, Projection):
        return resolved
    if not isinstance(resolved, _SectionSource):
        return Projection(resolved)
    relative = resolved.relative
    move_result = _project_move(request, section, resolved, files)
    if move_result is not None:
        if move_result.status != "projected":
            return move_result
        projected.extend(move_result.files)
        return None
    content = section_content(section, resolved.content)
    if content is None:
        return invalid_patch_projection(section.operation, relative)
    files[relative] = ProjectedFile(
        relative, content, section.operation, resolved.sha256
    )
    projected.append(files[relative])
    return None


def _project_patch(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode patch projection requested", tool=request.tool_name)
    text = patch_text(request.tool_input) or ""
    sections = parse_patch(text)
    if sections is None:
        return Projection("invalid")
    files: dict[str, ProjectedFile] = {}
    projected: list[ProjectedFile] = []
    for section in sections:
        result = _project_patch_section(request, section, files, projected)
        if result is not None:
            return result
    return Projection("projected", tuple(projected))


def unresolved_opencode_projection_finding(
    tool_name: str,
    tool_input: ObjectMapping,
    event_name: str,
) -> RuleFinding | None:
    """Return a deny finding when an OpenCode mutation cannot be projected safely."""
    logger.debug(
        "OpenCode unresolved projection evaluated", event=event_name, tool=tool_name
    )
    if event_name != PRE_TOOL_USE:
        return None
    projection = object_dict(tool_input.get(PROJECTION_KEY))
    status = string_value(projection.get("status")) or ""
    reason = string_value(projection.get("reason"))
    if status in {"projected", "unsupported"}:
        return None
    capability = opencode_tool_capability(tool_name)
    if capability is OpenCodeToolCapability.READ_ONLY:
        return None
    target_path = string_value(projection.get(METADATA_PATH))
    if reason == "target_outside_root":
        message = (
            "OpenCode target is outside the managed repository; refusing execution."
        )
    else:
        message = UNRESOLVED_PROJECTION_MESSAGES.get(
            status,
            "Unresolved OpenCode mutation projection; refusing execution.",
        )
    if target_path is not None:
        message = f"{message} Target: {target_path}."
    metadata: ObjectDict = {"projection_status": status or "missing"}
    if reason is not None:
        metadata["projection_reason"] = reason
    if target_path is not None:
        metadata[METADATA_PATH] = target_path
    return RuleFinding(
        rule_id="OC-PROJECTION-001",
        title="Unresolved OpenCode mutation projection",
        severity=Severity.CRITICAL,
        decision=DENY,
        message=message,
        metadata=metadata,
    )


def _session_scoped(request: ProjectionRequest) -> ProjectionRequest:
    """Split the caller's session directory from the containing repo root."""
    logger.debug("OpenCode session scope requested", tool=request.tool_name)
    directory = request.root.resolve()
    root = resolve_repo_root(directory) or directory
    return replace(request, root=root.resolve(), directory=directory)


def _project_scoped(request: ProjectionRequest) -> ObjectDict:
    logger.debug("OpenCode tool projection requested", tool=request.tool_name)
    if request.contract_version != OPENCODE_TOOL_CONTRACT_VERSION:
        return Projection("protocol_mismatch").to_dict()
    native_tool_id = native_opencode_mutation_tool_id(request.tool_name)
    projector = (
        {
            "write": _project_write,
            "edit": _project_edit,
            OPENCODE_PATCH_TOOL_ID: _project_patch,
        }.get(native_tool_id)
        if native_tool_id is not None
        else None
    )
    result = projector(request) if projector is not None else Projection("unsupported")
    return result.to_dict()


def project_opencode_tool_input(request: ProjectionRequest) -> ObjectDict:
    """Return projection metadata without mutating arguments or files."""
    logger.debug("OpenCode tool input projection requested", tool=request.tool_name)
    return _project_scoped(_session_scoped(request))


def normalize_projected_tool_input(request: ProjectionRequest) -> ObjectDict:
    """Return canonical analysis input containing complete projected edits."""
    logger.debug("OpenCode projection normalization requested", tool=request.tool_name)
    request = _session_scoped(request)
    projection = _project_scoped(request)
    enriched_input = dict(request.tool_input)
    enriched_input[PROJECTION_KEY] = projection
    if projection.get("status") != "projected":
        return enriched_input
    projected_edits: list[ObjectDict] = []
    for value in object_list(projection.get("files")):
        item = object_dict(value)
        relative = string_value(item.get(METADATA_PATH)) or ""
        # Absolute because rules variously resolve paths against cwd and repo root.
        edit: ObjectDict = {"file_path": str(request.root / relative)}
        if item.get("operation") == "delete":
            edit["operation"] = "delete"
        else:
            edit[METADATA_CONTENT] = item.get(METADATA_CONTENT, "")
        projected_edits.append(edit)
    enriched_input["edits"] = projected_edits
    if METADATA_PATH in enriched_input and projected_edits:
        # Targets dedupe by exact path, so one file must have one spelling.
        enriched_input[METADATA_PATH] = projected_edits[0]["file_path"]
    if native_opencode_mutation_tool_id(request.tool_name) == OPENCODE_PATCH_TOOL_ID:
        original_patch_text = patch_text(enriched_input) or ""
        enriched_input.pop("patchText", None)
        enriched_input.pop("patch_text", None)
        enriched_input["_slopgate_original_patch_text"] = original_patch_text
    return enriched_input
