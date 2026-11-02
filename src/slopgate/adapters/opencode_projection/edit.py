"""Filesystem targets and native OpenCode v2 exact-edit projection."""

from __future__ import annotations

import os
from pathlib import Path

from slopgate._types import string_value
from slopgate.util import logger

from .exact import replace_text
from .models import (
    ProjectedFile,
    Projection,
    ProjectionRequest,
    Snapshot,
    SnapshotStatus,
)
from .snapshot import read_snapshot


def _native_path(directory: Path, value: str) -> Path:
    """Resolve a tool path the way the host's FileAccess.resolvePath does."""
    logger.debug("OpenCode native path resolution requested", value=value)
    if value == "~":
        return Path.home()
    if value.startswith("~/") or (os.name == "nt" and value.startswith("~\\")):
        return Path.home() / value[2:]
    return directory / value


def _target(request: ProjectionRequest, value: str) -> tuple[Path, str] | Projection:
    logger.debug("OpenCode projection target requested", value=value)
    if not value.strip():
        return Projection("invalid")
    root = request.root.resolve()
    path = Path(os.path.abspath(_native_path(request.directory or root, value)))
    if not path.is_relative_to(root):
        return Projection("invalid", reason="target_outside_root")
    return path, path.relative_to(root).as_posix()


def _request_target(request: ProjectionRequest) -> tuple[Path, str] | Projection:
    logger.debug("OpenCode request target requested", tool=request.tool_name)
    return _target(request, string_value(request.tool_input.get("path")) or "")


def _snapshot_digest(root: Path, relative: str) -> str | None | SnapshotStatus:
    logger.debug("OpenCode snapshot requested", root=root, relative=relative)
    snapshot = read_snapshot(root, relative)
    if isinstance(snapshot, Snapshot):
        return snapshot.sha256
    return None if snapshot == "missing" else snapshot


def _project_edit(request: ProjectionRequest) -> Projection:
    logger.debug("OpenCode v2 edit projection requested", tool=request.tool_name)
    target = _request_target(request)
    if isinstance(target, Projection):
        return target
    _path, relative = target
    old = string_value(request.tool_input.get("oldString"))
    new = string_value(request.tool_input.get("newString"))
    replace_all = request.tool_input.get("replaceAll", False)
    if old is None or new is None or not isinstance(replace_all, bool):
        return Projection("invalid")
    snapshot = read_snapshot(request.root, relative)
    if not isinstance(snapshot, Snapshot):
        return Projection("invalid" if snapshot == "missing" else snapshot)
    bom = snapshot.content.startswith("\ufeff")
    source = snapshot.content.removeprefix("\ufeff")
    content = replace_text(source, old, new, replace_all)
    if content is None:
        return Projection("invalid")
    if bom and not content.startswith("\ufeff"):
        content = "\ufeff" + content
    return Projection(
        "projected", (ProjectedFile(relative, content, "edit", snapshot.sha256),)
    )
