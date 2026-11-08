"""Native package ownership refuses malformed evidence and tolerates probe errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.installer.native.packages import (
    StagingError,
    check_staging_owned,
    owned_staging_present,
)
from tests.native.packages_support import (
    HOST_NAME,
    empty_ownership_case,
    inject_probe_failure,
    staged_plan,
    tree_bytes,
)


def test_empty_ownership_file_map_refuses_nonempty_foreign_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, before = empty_ownership_case(tmp_path, monkeypatch)

    with pytest.raises(StagingError, match="foreign or malformed"):
        check_staging_owned(plan)

    assert tree_bytes(plan.entry_root) == before, (
        "empty ownership evidence must refuse without overwriting foreign staging files"
    )


@pytest.mark.parametrize(
    "failure_site", ("manifest_check", "directory_listing", "managed_file_read")
)
def test_owned_staging_probe_returns_false_on_oserror(
    failure_site: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = staged_plan(tmp_path, monkeypatch)
    inject_probe_failure(monkeypatch, plan, failure_site)

    assert not owned_staging_present(HOST_NAME), (
        f"owned staging discovery must not claim ownership after {failure_site} I/O failure"
    )
