"""Deterministic reconstruction of proposed complete Python files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectMapping, object_dict, object_list
from slopgate.constants import METADATA_PATH, REPLACE
from slopgate.context import HookContext
from slopgate.models import ContentTarget


@dataclass(frozen=True, slots=True)
class ProjectedFile:
    relative_path: str
    real_path: Path
    content: str


@dataclass(frozen=True, slots=True)
class ProjectedFiles:
    files: tuple[ProjectedFile, ...]


@dataclass(frozen=True, slots=True)
class ProjectionSkip:
    paths: tuple[str, ...]
    reason: str
    detail: str


ProjectionResult = ProjectedFiles | ProjectionSkip


def _normalized_target(repo_root: Path, path_value: str) -> tuple[Path, str] | None:
    root = repo_root.resolve()
    path = Path(path_value)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        return None
    return resolved, resolved.relative_to(root).as_posix()


def _python_targets(ctx: HookContext) -> tuple[tuple[Path, str], ...]:
    targets: list[tuple[Path, str]] = []
    for candidate in ctx.candidate_paths:
        if not candidate.lower().endswith(".py"):
            continue
        normalized = _normalized_target(ctx.config.repo_root, candidate)
        if normalized is not None and normalized not in targets:
            targets.append(normalized)
    return tuple(targets)


def _target_for_path(
    ctx: HookContext, real_path: Path, targets: list[ContentTarget]
) -> ContentTarget | None:
    for target in targets:
        normalized = _normalized_target(ctx.config.repo_root, target.path)
        if normalized is not None and normalized[0] == real_path:
            return target
    return None


def _mapping_string(mapping: ObjectMapping, keys: tuple[str, ...]) -> tuple[bool, str]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            return True, value
    return False, ""


def _apply_edit(content: str, edit: ObjectMapping) -> str | None:
    old_present, old_text = _mapping_string(
        edit, ("old_string", "oldString", "old_text", "oldText")
    )
    new_present, new_text = _mapping_string(
        edit, ("new_string", "newString", "new_text", "newText")
    )
    if not old_present or not new_present or not old_text:
        return None
    count = content.count(old_text)
    replace_all = edit.get("replace_all") is True or edit.get("replaceAll") is True
    if count == 0 or (count != 1 and not replace_all):
        return None
    return content.replace(old_text, new_text, -1 if replace_all else 1)


def _project_write(
    ctx: HookContext, targets: tuple[tuple[Path, str], ...]
) -> ProjectionResult:
    files: list[ProjectedFile] = []
    complete_targets = [
        target for target in ctx.content_targets if target.source == "tool_input"
    ]
    for real_path, relative_path in targets:
        target = _target_for_path(ctx, real_path, complete_targets)
        if target is None:
            return ProjectionSkip(
                (relative_path,),
                "missing_complete_content",
                "Write payload did not expose complete file content.",
            )
        files.append(ProjectedFile(relative_path, real_path, target.content))
    return ProjectedFiles(tuple(files))


def _project_single_edit(
    ctx: HookContext, targets: tuple[tuple[Path, str], ...]
) -> ProjectionResult:
    if len(targets) != 1:
        return ProjectionSkip(
            tuple(relative for _real, relative in targets),
            "ambiguous_edit_targets",
            "Structured Edit projection requires exactly one Python target.",
        )
    real_path, relative_path = targets[0]
    try:
        current = real_path.read_text(encoding="utf-8")
    except OSError:
        return ProjectionSkip(
            (relative_path,),
            "missing_edit_base",
            "Structured Edit projection could not read the current file.",
        )
    projected = _apply_edit(current, ctx.tool_input)
    if projected is None:
        return ProjectionSkip(
            (relative_path,),
            "ambiguous_edit_content",
            "Structured Edit did not identify one deterministic replacement.",
        )
    return ProjectedFiles((ProjectedFile(relative_path, real_path, projected),))


def _project_multi_edit(
    ctx: HookContext, targets: tuple[tuple[Path, str], ...]
) -> ProjectionResult:
    edits_by_path: dict[str, list[ObjectMapping]] = {}
    fallback = targets[0][1] if len(targets) == 1 else ""
    for item in object_list(ctx.tool_input.get("edits")):
        edit = object_dict(item)
        path_present, path_value = _mapping_string(
            edit, ("file_path", "filePath", METADATA_PATH)
        )
        relative = path_value if path_present else fallback
        if relative:
            edits_by_path.setdefault(relative, []).append(edit)
    files: list[ProjectedFile] = []
    for real_path, relative_path in targets:
        edits = edits_by_path.get(relative_path)
        if not edits:
            return ProjectionSkip(
                (relative_path,),
                "missing_edit_content",
                "MultiEdit did not expose structured edits for the target.",
            )
        try:
            projected = real_path.read_text(encoding="utf-8")
        except OSError:
            return ProjectionSkip(
                (relative_path,),
                "missing_edit_base",
                "MultiEdit projection could not read the current file.",
            )
        for edit in edits:
            updated = _apply_edit(projected, edit)
            if updated is None:
                return ProjectionSkip(
                    (relative_path,),
                    "ambiguous_edit_content",
                    "MultiEdit included a non-deterministic replacement.",
                )
            projected = updated
        files.append(ProjectedFile(relative_path, real_path, projected))
    return ProjectedFiles(tuple(files))


def build_projection(ctx: HookContext) -> ProjectionResult:
    """Build complete projected files or a traceable reason to defer to post-edit."""

    targets = _python_targets(ctx)
    if not targets:
        return ProjectionSkip(
            (), "no_python_targets", "No Python target was identified."
        )
    if ctx.shell_command:
        return ProjectionSkip(
            tuple(relative for _real, relative in targets),
            "incomplete_shell_content",
            "Shell writes may append or partially mutate files, so projection was skipped.",
        )
    tool_name = ctx.tool_name.strip().lower().replace("_", "").replace("-", "")
    if tool_name == "write":
        return _project_write(ctx, targets)
    if tool_name == "multiedit":
        return _project_multi_edit(ctx, targets)
    if tool_name in {"edit", REPLACE, "strreplace"} or "editfile" in tool_name:
        return _project_single_edit(ctx, targets)
    return ProjectionSkip(
        tuple(relative for _real, relative in targets),
        "unsupported_projection_tool",
        f"{ctx.tool_name} does not expose a complete deterministic projection.",
    )


__all__ = [
    "ProjectedFile",
    "ProjectedFiles",
    "ProjectionResult",
    "ProjectionSkip",
    "build_projection",
]
