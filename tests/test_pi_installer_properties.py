from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

import slopgate.installer._pi as pi_installer
import slopgate.installer._shared as shared_installer

_PI_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_TEXT_FRAGMENT = st.text(alphabet=list("abcXYZ012 _-."), max_size=20)
_BINARY_TEXT = st.text(alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20)
_INSTALL_SCOPE = st.sampled_from(["user", "project", "both"])


def install_status_for_scope(scope: str, dry_run: bool) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        project_root = temp_path / "repo"
        project_root.mkdir()
        home_path = temp_path / "home"
        with (
            patch.object(Path, "home", return_value=home_path),
            patch.object(shared_installer, "find_binary", return_value="/tmp/slopgate"),
        ):
            return pi_installer.install_pi(
                dry_run=dry_run, scope=scope, project_root=project_root
            )


def uninstall_status_for_scope(scope: str, dry_run: bool) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        project_root = temp_path / "repo"
        project_root.mkdir()
        home_path = temp_path / "home"
        with (
            patch.object(Path, "home", return_value=home_path),
            patch.object(shared_installer, "find_binary", return_value="/tmp/slopgate"),
        ):
            pi_installer.install_pi(
                dry_run=False, scope="both", project_root=project_root
            )
            return pi_installer.uninstall_pi(
                dry_run=dry_run, scope=scope, project_root=project_root
            )


@given(prefix=_TEXT_FRAGMENT, suffix=_TEXT_FRAGMENT, binary=_BINARY_TEXT)
def test_render_pi_extension_replaces_exact_placeholder_property(
    prefix: str, suffix: str, binary: str
) -> None:
    template = f"{prefix}{_PI_PLACEHOLDER}{suffix}"
    rendered = pi_installer.render_pi_extension(template, binary)
    expected = f"{prefix}{json.dumps(shared_installer.base_invocation(binary))}{suffix}"
    assert rendered == expected, (
        "render_pi_extension must replace only the argv placeholder"
    )


@given(scope=_INSTALL_SCOPE, dry_run=st.booleans())
def test_install_pi_scope_status_property(scope: str, dry_run: bool) -> None:
    assert install_status_for_scope(scope, dry_run) == 0, (
        "install_pi should accept every normalized scope in dry and write modes"
    )


@given(scope=_INSTALL_SCOPE, dry_run=st.booleans())
def test_uninstall_pi_scope_status_property(scope: str, dry_run: bool) -> None:
    assert uninstall_status_for_scope(scope, dry_run) == 0, (
        "uninstall_pi should accept every normalized scope in dry and write modes"
    )
