"""Contract for flat-sibling path and patch helpers."""

from __future__ import annotations

from slopgate.rules.python_ast._rules.sibling_files import (
    PythonFlatFileSiblingsRule,
    flat_sibling_patch_added_and_removed_paths,
    flat_sibling_patch_blob,
    flat_sibling_projected_removed_files,
)
from slopgate.util.path_filters import PYTHON_SOURCE_SUFFIXES
from slopgate.rules.python_ast._rules.sibling_files.groups import (
    build_pkg_block,
    sibling_group_message,
)
from slopgate.rules.python_ast._rules.sibling_files.paths import prefix_for_name


def test_prefix_for_name_reads_public_prefix() -> None:
    prefix = prefix_for_name("result_models.py")
    assert prefix == "result"


def test_prefix_for_name_ignores_test_prefix() -> None:
    prefix = prefix_for_name("test_helpers.py")
    assert prefix is None


def test_flat_file_siblings_rule_id() -> None:
    assert PythonFlatFileSiblingsRule.rule_id == "PY-CODE-017"


def test_flat_sibling_patch_blob_name() -> None:
    assert flat_sibling_patch_blob.__name__ == "flat_sibling_patch_blob"


def test_build_pkg_block_lists_child_module() -> None:
    block = build_pkg_block(["result_models.py"], "result")
    assert block == "        models.py"


def test_sibling_group_message_names_directory() -> None:
    message = sibling_group_message("agents", "result", "result_models.py", "ready")
    assert "agents/" in message


def test_patch_added_and_removed_paths_reads_delete() -> None:
    added, removed = flat_sibling_patch_added_and_removed_paths(
        "*** Delete File: src/result_models.py\n"
    )
    assert (added, removed) == ([], ["src/result_models.py"])


def test_python_source_suffixes_are_ordered() -> None:
    assert PYTHON_SOURCE_SUFFIXES[0] < PYTHON_SOURCE_SUFFIXES[1]


def test_projected_removed_files_name() -> None:
    assert (
        flat_sibling_projected_removed_files.__name__
        == "flat_sibling_projected_removed_files"
    )
