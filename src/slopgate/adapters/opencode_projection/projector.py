"""Filesystem-aware OpenCode mutation projection orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import METADATA_CONTENT, METADATA_PATH
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
from slopgate.util import logger


@dataclass(frozen=True, slots=True)
class _SectionSource:
    content: str
    sha256: str | None


def _target(root: Path, value: str) -> tuple[Path, str] | None:
    logger.debug("OpenCode projection target resolved", path=value)
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
    logger.debug(
        "OpenCode projection request target extracted",
        tool_name=request.tool_name,
    )
    raw_path = string_value(request.tool_input.get("filePath")) or ""
    return _target(request.root, raw_path)


def _project_write(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode write projection started")
    target = _request_target(request)
    content = string_value(request.tool_input.get(METADATA_CONTENT))
    if target is None or content is None:
        return Projection("invalid")
    _path, relative = target
    match read_snapshot(request.root, relative):
        case Snapshot(sha256=sha256):
            digest: str | None = sha256
        case "missing":
            digest = None
        case "invalid" | "stale" as status:
            return Projection(status)
    return Projection(
        "projected",
        (ProjectedFile(relative, content, "write", digest),),
    )


def _project_edit(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode edit projection started")
    target = _request_target(request)
    old = string_value(request.tool_input.get("oldString"))
    new = string_value(request.tool_input.get("newString"))
    if target is None or not old or new is None:
        return Projection("invalid")
    _path, relative = target
    match read_snapshot(request.root, relative):
        case Snapshot(content=source, sha256=sha256):
            pass
        case "missing":
            return Projection("invalid")
        case "invalid" | "stale" as status:
            return Projection(status)
    count = source.count(old)
    replace_all = request.tool_input.get("replaceAll") is True
    if count == 0 or (not replace_all and count != 1):
        return Projection("invalid")
    content = source.replace(old, new, -1 if replace_all else 1)
    return Projection(
        "projected",
        (ProjectedFile(relative, content, "edit", sha256),),
    )


def _section_source(
    root: Path,
    section: PatchSection,
) -> _SectionSource | SnapshotStatus:
    logger.debug(
        "OpenCode patch section source resolved",
        path=section.path,
        operation=section.operation,
    )
    target = _target(root, section.path)
    if target is None:
        return "invalid"
    _path, relative = target
    match read_snapshot(root, relative):
        case Snapshot(content=content, sha256=sha256):
            if section.operation == "add":
                return "invalid"
            return _SectionSource(content, sha256)
        case "missing":
            return _SectionSource("", None) if section.operation == "add" else "invalid"
        case "invalid" | "stale" as status:
            return status


def _section_content(
    section: PatchSection,
    source: str,
) -> str | None:
    logger.debug(
        "OpenCode patch section applied",
        path=section.path,
        operation=section.operation,
    )
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


def _project_patch(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode apply_patch projection started")
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
        match _section_source(request.root, section):
            case _SectionSource(content=source, sha256=digest):
                pass
            case "missing":
                return Projection("invalid")
            case "invalid" | "stale" as status:
                return Projection(status)
        content = _section_content(section, source)
        if content is None:
            return Projection("invalid")
        files[relative] = ProjectedFile(
            relative,
            content,
            section.operation,
            digest,
        )
    return Projection("projected", tuple(files.values()))


def project_opencode_tool_input(request: ProjectionRequest) -> ObjectDict:
    """Return projection metadata without mutating arguments or files."""
    logger.debug(
        "OpenCode tool projection started",
        tool_name=request.tool_name,
        contract_version=request.contract_version,
    )
    if request.contract_version != OPENCODE_TOOL_CONTRACT_VERSION:
        return Projection("unsupported").to_dict()
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
    logger.debug("OpenCode projected tool input normalized")
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
