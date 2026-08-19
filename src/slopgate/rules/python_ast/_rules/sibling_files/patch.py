"""Parse patch payloads that add, delete, or move flat sibling files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.util.path_filters import is_authored_python_path
from slopgate.util.payloads import first_present

from .paths import flat_sibling_resolve_candidate_path, prefix_for_name

if TYPE_CHECKING:
    from slopgate.context import HookContext


def flat_sibling_patch_blob(ctx: HookContext) -> str:
    """Return patch text from the hook payload, or empty when absent."""
    blob = first_present(ctx.tool_input, ("patch", "patchText", "patch_text"))
    if not isinstance(blob, str):
        return ""
    if blob == "":
        return ""
    return blob


def flat_sibling_patch_added_and_removed_paths(
    patch_blob: str,
) -> tuple[list[str], list[str]]:
    """Return added and removed paths parsed from a patch blob."""
    added: list[str] = []
    removed: list[str] = []
    current_update_path = ""
    for line in patch_blob.splitlines():
        if line.startswith("*** Update File: "):
            current_update_path = line.replace("*** Update File: ", "", 1).strip()
            continue
        if line.startswith("*** Add File: "):
            added.append(line.replace("*** Add File: ", "", 1).strip())
            current_update_path = ""
            continue
        if line.startswith("*** Delete File: "):
            removed.append(line.replace("*** Delete File: ", "", 1).strip())
            current_update_path = ""
            continue
        if line.startswith("*** Move to: "):
            if current_update_path:
                removed.append(current_update_path)
            added.append(line.replace("*** Move to: ", "", 1).strip())
            current_update_path = ""
    return (added, removed)


def flat_sibling_projected_removed_files(ctx: HookContext) -> dict[Path, set[str]]:
    """Return flat sibling filenames a patch is deleting/moving away."""
    patch_blob = flat_sibling_patch_blob(ctx)
    if not patch_blob:
        return {}
    _, removed_paths = flat_sibling_patch_added_and_removed_paths(patch_blob)
    removed_by_parent: dict[Path, set[str]] = {}
    for path_value in removed_paths:
        if not is_authored_python_path(path_value):
            continue
        full = flat_sibling_resolve_candidate_path(ctx, path_value)
        prefix = prefix_for_name(full.name)
        if prefix is None:
            continue
        removed_by_parent.setdefault(full.parent, set()).add(full.name)
    return removed_by_parent
