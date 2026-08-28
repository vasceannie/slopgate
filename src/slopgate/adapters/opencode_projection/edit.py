"""Native OpenCode edit projection behavior."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from slopgate._types import ObjectMapping, string_value
from slopgate.util import logger

from .hashline import project_hashline_edits
from .models import ProjectedFile, Projection, ProjectionRequest, Snapshot, SnapshotStatus
from .snapshot import read_snapshot


@dataclass(frozen=True, slots=True)
class _EditContent:
    content: str
    source_digest: str | None
    source_exists: bool


def _target(root: Path, value: str) -> tuple[Path, str] | Projection:
    logger.debug("OpenCode projection target requested", root=root, value=value)
    if not value.strip():
        return Projection("invalid")
    root = root.resolve()
    candidate = Path(value)
    raw_path = candidate if candidate.is_absolute() else root / candidate
    path = Path(os.path.abspath(raw_path))
    if not path.is_relative_to(root):
        return Projection("invalid", reason="target_outside_root")
    return path, path.relative_to(root).as_posix()


def _request_target(request: ProjectionRequest) -> tuple[Path, str] | Projection:
    logger.debug("OpenCode request target requested", tool=request.tool_name)
    raw_path = string_value(request.tool_input.get("filePath")) or ""
    return _target(request.root, raw_path)


def _snapshot_digest(root: Path, relative: str) -> str | None | SnapshotStatus:
    logger.debug("OpenCode snapshot requested", root=root, relative=relative)
    snapshot = read_snapshot(root, relative)
    if isinstance(snapshot, Snapshot):
        return snapshot.sha256
    if snapshot == "missing":
        return None
    return snapshot


def _native_edit_delete_mode(tool_input: ObjectMapping) -> bool | Projection:
    logger.debug("OpenCode native delete mode evaluated")
    delete_value = tool_input.get("delete")
    if "delete" in tool_input and not isinstance(delete_value, bool):
        return Projection("invalid")
    return delete_value is True


def _native_edit_rename(tool_input: ObjectMapping) -> str | None | Projection:
    logger.debug("OpenCode native rename evaluated")
    if "rename" not in tool_input:
        return None
    rename = string_value(tool_input.get("rename"))
    return rename if rename is not None else Projection("invalid")


def _validate_native_edit_shape(
    tool_input: ObjectMapping, delete_mode: bool, rename: str | None
) -> Projection | None:
    logger.debug("OpenCode native edit shape evaluated")
    raw_edits = tool_input.get("edits")
    if delete_mode:
        if rename or not isinstance(raw_edits, list) or raw_edits:
            return Projection("invalid")
        return None
    if rename is not None and "edits" not in tool_input:
        return Projection("invalid")
    if "edits" in tool_input and (
        not isinstance(raw_edits, list) or not raw_edits
    ):
        return Projection("invalid")
    return None


def _native_edit_options(
    tool_input: ObjectMapping,
) -> tuple[bool, str | None] | Projection:
    logger.debug("OpenCode native edit options evaluated")
    delete_mode = _native_edit_delete_mode(tool_input)
    if isinstance(delete_mode, Projection):
        return delete_mode
    rename = _native_edit_rename(tool_input)
    if isinstance(rename, Projection):
        return rename
    shape_error = _validate_native_edit_shape(tool_input, delete_mode, rename)
    return shape_error if shape_error is not None else (delete_mode, rename)


def _project_edit_content(
    request: ProjectionRequest,
    snapshot: Snapshot | Literal["missing"],
) -> _EditContent | Projection:
    logger.debug("OpenCode edit content projection requested")
    source_exists = isinstance(snapshot, Snapshot)
    source_content = snapshot.content if source_exists else ""
    source_digest = snapshot.sha256 if source_exists else None
    tool_input = request.tool_input
    if "edits" in tool_input:
        hashline_result = project_hashline_edits(
            source_content, tool_input.get("edits")
        )
        if hashline_result.content is None:
            return Projection("invalid", reason=hashline_result.failure)
        return _EditContent(hashline_result.content, source_digest, source_exists)
    if not source_exists:
        return Projection("invalid")
    old = string_value(tool_input.get("oldString"))
    new = string_value(tool_input.get("newString"))
    if not old or new is None:
        return Projection("invalid")
    count = source_content.count(old)
    replace_all = tool_input.get("replaceAll") is True
    if count == 0 or (not replace_all and count != 1):
        return Projection("invalid")
    content = source_content.replace(old, new, -1 if replace_all else 1)
    return _EditContent(content, source_digest, True)


def _project_renamed_edit(
    request: ProjectionRequest,
    relative: str,
    edit: _EditContent,
    rename: str,
) -> Projection:
    logger.debug("OpenCode renamed edit projection requested", path=relative)
    destination = _target(request.root, rename)
    if isinstance(destination, Projection):
        return destination
    _destination_path, destination_relative = destination
    operation = "edit" if edit.source_exists else "add"
    if destination_relative == relative:
        return Projection(
            "projected",
            (ProjectedFile(relative, edit.content, operation, edit.source_digest),),
        )
    if _snapshot_digest(request.root, destination_relative) is not None:
        return Projection("invalid")
    files: list[ProjectedFile] = []
    if edit.source_exists:
        files.append(ProjectedFile(relative, "", "delete", edit.source_digest))
    files.append(ProjectedFile(destination_relative, edit.content, "add", None))
    return Projection("projected", tuple(files))


def _project_edit(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode edit projection requested", tool=request.tool_name)
    target = _request_target(request)
    if isinstance(target, Projection):
        return target
    _path, relative = target
    options = _native_edit_options(request.tool_input)
    if isinstance(options, Projection):
        return options
    delete_mode, rename = options
    snapshot = read_snapshot(request.root, relative)
    if delete_mode:
        if not isinstance(snapshot, Snapshot):
            return Projection(snapshot if snapshot != "missing" else "invalid")
        return Projection(
            "projected",
            (ProjectedFile(relative, "", "delete", snapshot.sha256),),
        )
    if snapshot not in ("missing",) and not isinstance(snapshot, Snapshot):
        return Projection(snapshot)
    edit = _project_edit_content(request, snapshot)
    if isinstance(edit, Projection):
        return edit
    if rename is not None:
        return _project_renamed_edit(request, relative, edit, rename)
    operation = "edit" if edit.source_exists else "add"
    return Projection(
        "projected",
        (ProjectedFile(relative, edit.content, operation, edit.source_digest),),
    )
