"""Name coverage for remaining store mutation helpers."""

from __future__ import annotations

from slopgate.lint.project_index.store import (
    delete_files,
    load_violations_for_hashes,
    replace_file_violations,
    summary_from_row,
    upsert_file,
)


def test_store_row_helper_names() -> None:
    assert (
        delete_files.__name__,
        load_violations_for_hashes.__name__,
        replace_file_violations.__name__,
        summary_from_row.__name__,
        upsert_file.__name__,
    ) == (
        "delete_files",
        "load_violations_for_hashes",
        "replace_file_violations",
        "summary_from_row",
        "upsert_file",
    )
