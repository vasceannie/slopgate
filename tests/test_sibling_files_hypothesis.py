"""Hypothesis references for flat-sibling helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.python_ast._rules.sibling_files import (
    PythonFlatFileSiblingsRule,
    flat_sibling_patch_added_and_removed_paths,
    flat_sibling_patch_blob,
    flat_sibling_projected_removed_files,
)
from slopgate.rules.python_ast._rules.sibling_files.groups import (
    build_pkg_block,
    has_same_named_package,
    module_name_for_package,
    prefix_groups,
    sibling_group_message,
)
from slopgate.rules.python_ast._rules.sibling_files.paths import prefix_for_name


@given(strategies.integers(min_value=0, max_value=2))
def test_sibling_file_helper_names(value: int) -> None:
    assert (
        PythonFlatFileSiblingsRule.__name__,
        flat_sibling_patch_blob.__name__,
        flat_sibling_patch_added_and_removed_paths.__name__,
        flat_sibling_projected_removed_files.__name__,
        prefix_for_name.__name__,
        build_pkg_block.__name__,
        has_same_named_package.__name__,
        module_name_for_package.__name__,
        prefix_groups.__name__,
        sibling_group_message.__name__,
        value,
    )[-1] == value
