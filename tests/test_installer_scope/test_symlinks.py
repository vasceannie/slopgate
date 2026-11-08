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
    refuse_opencode_project_symlink,
    refuse_project_symlink,
    refuse_user_leaf_symlink,
)
from tests.native.hosts import FakeHosts

pytestmark = pytest.mark.usefixtures("native_hosts")


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


@pytest.mark.parametrize("case", PROJECT_INSTALLERS)
def test_project_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[Callable[..., int], str],
    native_hosts: FakeHosts,
) -> None:
    install, relative_leaf = case
    leaf, _external = refuse_project_symlink(
        tmp_path, monkeypatch, install, relative_leaf, "leaf"
    )
    assert leaf.is_symlink(), "the planted leaf symlink must not be replaced"
    assert native_hosts.mutating_calls() == [], (
        "project preflight must refuse before any native manager mutation"
    )
    assert not native_hosts.staging_root.exists(), (
        "a rejected project install must not create native staging files"
    )


@pytest.mark.parametrize("case", PROJECT_INSTALLERS)
def test_project_scope_refuses_parent_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[Callable[..., int], str],
    native_hosts: FakeHosts,
) -> None:
    install, relative_leaf = case
    _leaf, external = refuse_project_symlink(
        tmp_path, monkeypatch, install, relative_leaf, "parent"
    )
    assert external.read_text(encoding="utf-8") == KEEP_TEXT, (
        "parent symlink refusal must leave the external target unchanged"
    )
    assert native_hosts.mutating_calls() == [], (
        "project preflight must refuse before any native manager mutation"
    )
    assert not native_hosts.staging_root.exists(), (
        "a rejected project install must not create native staging files"
    )


@pytest.mark.parametrize(("install", "relative_leaf"), USER_INSTALLERS)
def test_user_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> None:
    status, target, outside = refuse_user_leaf_symlink(
        tmp_path, monkeypatch, install, relative_leaf
    )

    assert status == 1, "user install must refuse a leaf symlink"
    assert outside.read_text(encoding="utf-8") == KEEP_TEXT, (
        "external symlink targets must remain unchanged"
    )
    assert target.is_symlink(), "the planted leaf symlink must not be replaced"
