"""Symlink-escape refusals for project and user install scopes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from .support import (
    KEEP_TEXT,
    OPENCODE_LEAF_CASES,
    OPENCODE_PARENT_CASES,
    PROJECT_INSTALLERS,
    USER_INSTALLERS,
    plant_user_leaf_symlink,
    refuse_opencode_project_symlink,
    refuse_project_symlink,
    stub_binary,
)


@pytest.mark.parametrize("dry_run", OPENCODE_LEAF_CASES)
def test_opencode_project_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dry_run: bool,
) -> None:
    plugin, _external = refuse_opencode_project_symlink(
        tmp_path, monkeypatch, "leaf", dry_run
    )
    assert plugin.is_symlink(), "the planted leaf symlink must not be replaced"


@pytest.mark.parametrize(("kind", "dry_run"), OPENCODE_PARENT_CASES)
def test_opencode_project_scope_refuses_parent_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    dry_run: bool,
) -> None:
    _plugin, external = refuse_opencode_project_symlink(
        tmp_path, monkeypatch, kind, dry_run
    )
    assert external.read_text(encoding="utf-8") == KEEP_TEXT, (
        "parent symlink refusal must leave the external target unchanged"
    )


@pytest.mark.parametrize(("install", "relative_leaf"), PROJECT_INSTALLERS)
def test_project_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> None:
    leaf, _external = refuse_project_symlink(
        tmp_path, monkeypatch, install, relative_leaf, "leaf"
    )
    assert leaf.is_symlink(), "the planted leaf symlink must not be replaced"


@pytest.mark.parametrize(("install", "relative_leaf"), PROJECT_INSTALLERS)
def test_project_scope_refuses_parent_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> None:
    _leaf, external = refuse_project_symlink(
        tmp_path, monkeypatch, install, relative_leaf, "parent"
    )
    assert external.read_text(encoding="utf-8") == KEEP_TEXT, (
        "parent symlink refusal must leave the external target unchanged"
    )


@pytest.mark.parametrize(("install", "relative_leaf"), USER_INSTALLERS)
def test_user_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    stub_binary(monkeypatch)
    target, outside = plant_user_leaf_symlink(tmp_path, relative_leaf)
    assert install(dry_run=False, scope="user") == 1, (
        "user install must refuse a leaf symlink"
    )
    assert outside.read_text(encoding="utf-8") == KEEP_TEXT, (
        "external symlink targets must remain unchanged"
    )
    assert target.is_symlink(), "the planted leaf symlink must not be replaced"
