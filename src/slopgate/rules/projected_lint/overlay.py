"""Minimal temporary repository overlays for projected lint."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from slopgate.rules.projected_lint.projection import ProjectedFile


@dataclass(frozen=True, slots=True)
class ProjectedOverlay:
    root: Path
    files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class OverlayUnavailableError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _copy_current_config(repo_root: Path, overlay_root: Path) -> None:
    source = repo_root / "slopgate.toml"
    if not source.is_file():
        return
    (overlay_root / "slopgate.toml").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _write_projected_file(overlay_root: Path, projected: ProjectedFile) -> Path:
    target = overlay_root / projected.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = target.parent.resolve()
    if not resolved_parent.is_relative_to(overlay_root.resolve()):
        raise OverlayUnavailableError("projected path escaped the temporary overlay")
    if target.is_symlink():
        target.unlink()
    target.write_text(projected.content, encoding="utf-8")
    return target


@contextmanager
def projected_overlay(
    repo_root: Path, projected_files: tuple[ProjectedFile, ...]
) -> Iterator[ProjectedOverlay]:
    """Yield a disposable repository tree containing only proposed mutations."""

    with tempfile.TemporaryDirectory(prefix="slopgate-projected-lint-") as tmpdir:
        root = Path(tmpdir)
        try:
            _copy_current_config(repo_root, root)
            files = tuple(_write_projected_file(root, item) for item in projected_files)
        except OSError as exc:
            raise OverlayUnavailableError(
                "projected files could not be materialized in the temporary overlay"
            ) from exc
        yield ProjectedOverlay(root=root, files=files)


__all__ = ["OverlayUnavailableError", "ProjectedOverlay", "projected_overlay"]
