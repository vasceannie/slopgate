from __future__ import annotations

from pathlib import Path

from slopgate.installer.install_flow import rollback_completed_installs


def test_rollback_completed_installs_calls_uninstall_for_each_path(
    tmp_path: Path,
) -> None:
    completed = [tmp_path / "one", tmp_path / "two"]
    removed: list[Path] = []

    def uninstall(path: Path) -> int:
        removed.append(path)
        return 0

    rollback_completed_installs(completed, uninstall)

    assert removed == completed, (
        "rollback_completed_installs should invoke uninstall for every completed path"
    )
