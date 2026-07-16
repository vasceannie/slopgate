from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.context import build_context
from slopgate.rules.projected_lint.overlay import (
    OverlayUnavailableError,
    ProjectedOverlay,
    projected_overlay,
)
from slopgate.rules.projected_lint.projection import (
    ProjectedFile,
    ProjectedFiles,
    build_projection,
)
from tests.projected_lint.support import BAD_LINE, edit_payload


def test_edit_projection_reconstructs_complete_file_without_mutating_repo(
    projected_repo: Path,
) -> None:
    original = (projected_repo / "src/app.py").read_text(encoding="utf-8")
    ctx = build_context(edit_payload(projected_repo))

    projection = build_projection(ctx)

    assert isinstance(projection, ProjectedFiles), "Edit should be reconstructable"
    assert projection.files[0].content == original.replace(
        "    return 1\n", BAD_LINE
    ), "Projection should contain the complete edited file"
    assert (projected_repo / "src/app.py").read_text(encoding="utf-8") == original, (
        "Projection must not mutate the real repository"
    )


def test_overlay_restores_real_paths_and_cleans_up_after_success(
    projected_repo: Path,
) -> None:
    projection = _projected_files(projected_repo)

    with projected_overlay(projected_repo, projection.files) as overlay:
        overlay_root = overlay.root
        projected_path = overlay.files[0]
        assert isinstance(overlay, ProjectedOverlay), (
            "Overlay should expose typed root and materialized files"
        )
        assert projected_path.relative_to(overlay_root).as_posix() == "src/app.py", (
            "Overlay should preserve repository-relative paths"
        )
        assert projected_path.read_text(encoding="utf-8").endswith(BAD_LINE), (
            "Overlay should contain proposed content"
        )

    assert not overlay_root.exists(), "Overlay should clean up after success"


def test_overlay_cleans_up_after_exception(projected_repo: Path) -> None:
    projection = build_projection(build_context(edit_payload(projected_repo)))
    assert isinstance(projection, ProjectedFiles), "Fixture edit should project"
    overlay_root: Path | None = None

    with pytest.raises(RuntimeError, match="forced failure"):
        with projected_overlay(projected_repo, projection.files) as overlay:
            overlay_root = overlay.root
            raise RuntimeError("forced failure")

    assert overlay_root is not None and not overlay_root.exists(), (
        "Overlay should clean up after exceptions"
    )


def test_overlay_cleans_up_on_cancellation_equivalent_exit(
    projected_repo: Path,
) -> None:
    projection = _projected_files(projected_repo)
    manager = projected_overlay(projected_repo, projection.files)
    overlay = manager.__enter__()

    _ = manager.__exit__(GeneratorExit, GeneratorExit(), None)

    assert not overlay.root.exists(), "GeneratorExit should clean up the overlay"


def test_overlay_rejects_projected_paths_that_escape_repo(projected_repo: Path) -> None:
    escaped = ProjectedFile(
        relative_path="../escape.py",
        real_path=projected_repo.parent / "escape.py",
        content="escaped = True\n",
    )

    with pytest.raises(OverlayUnavailableError):
        with projected_overlay(projected_repo, (escaped,)):
            raise AssertionError("Escaped projected paths must not materialize")


def _projected_files(repo: Path) -> ProjectedFiles:
    projection = build_projection(build_context(edit_payload(repo)))
    if not isinstance(projection, ProjectedFiles):
        raise AssertionError("Fixture edit should project")
    return projection
