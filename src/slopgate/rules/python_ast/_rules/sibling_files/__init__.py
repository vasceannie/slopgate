"""Detect flat prefix_* sibling files that should become a package."""

from .paths import FlatSiblingFindingInput, flat_sibling_resolve_candidate_path
from .patch import (
    flat_sibling_patch_added_and_removed_paths,
    flat_sibling_patch_blob,
    flat_sibling_projected_removed_files,
)
from .rule import PythonFlatFileSiblingsRule

__all__ = [
    "FlatSiblingFindingInput",
    "PythonFlatFileSiblingsRule",
    "flat_sibling_patch_added_and_removed_paths",
    "flat_sibling_patch_blob",
    "flat_sibling_projected_removed_files",
    "flat_sibling_resolve_candidate_path",
]
