"""Native install entry dispatch preserves normalized request invariants."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies

import slopgate.installer.native.entry
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer.native.entry import run_native_install
from slopgate.installer.native.model import NativeRequest, expand_scopes

BINARY = "resolved-slopgate"
SCOPES = (INSTALL_SCOPE_BOTH, INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER)
Dispatch = tuple[tuple[str, ...], Path, bool, str]


class _RecordingInstaller:
    """Installer callback that records each normalized dispatch it receives."""

    def __init__(self) -> None:
        self.calls: list[Dispatch] = []

    def __call__(self, request: NativeRequest, binary: str) -> int:
        self.calls.append((request.scopes, request.root, request.dry_run, binary))
        return 0


@contextmanager
def _resolved_binary() -> Generator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(slopgate.installer.native.entry, "find_binary", lambda: BINARY)
        yield


def _expected_dispatch(scope: str, root: Path, dry_run: bool) -> Dispatch:
    return (expand_scopes(scope), root.resolve(), dry_run, BINARY)


REQUEST_CASES = strategies.tuples(
    strategies.sampled_from(SCOPES), strategies.booleans()
)


@settings(max_examples=20, deadline=None)
@given(case=REQUEST_CASES)
def test_run_native_install_dispatches_normalized_scope_and_root_property(
    case: tuple[str, bool],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    scope, dry_run = case
    root = tmp_path_factory.mktemp("native-install-entry")
    installer = _RecordingInstaller()
    with _resolved_binary():
        status = run_native_install(scope, root, dry_run, installer)

    assert status == 0, "valid scope requests must dispatch successfully"
    assert installer.calls == [_expected_dispatch(scope, root, dry_run)], (
        "native entry dispatch must normalize scopes, resolve root, preserve "
        "dry-run, and pass the resolved binary"
    )
