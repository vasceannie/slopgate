from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies

import slopgate.installer._pi
import slopgate.installer._shared

_PI_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_TEXT_FRAGMENT = strategies.text(alphabet=list("abcXYZ012 _-."), max_size=20)
_BINARY_TEXT = strategies.text(
    alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20
)
_INSTALL_SCOPE = strategies.sampled_from(["user", "project", "both"])
_PI_MARKER_SUBSET = strategies.frozensets(
    strategies.sampled_from(slopgate.installer._pi.PI_OWNERSHIP_MARKERS)
)


def install_status_for_scope(scope: str, dry_run: bool) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        project_root = temp_path / "repo"
        project_root.mkdir()
        home_path = temp_path / "home"
        with (
            patch.object(Path, "home", return_value=home_path),
            patch.object(
                slopgate.installer._shared,
                "find_binary",
                return_value="/tmp/slopgate",
            ),
        ):
            return slopgate.installer._pi.install_pi(
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
            patch.object(
                slopgate.installer._shared,
                "find_binary",
                return_value="/tmp/slopgate",
            ),
        ):
            slopgate.installer._pi.install_pi(
                dry_run=False, scope="both", project_root=project_root
            )
            return slopgate.installer._pi.uninstall_pi(
                dry_run=dry_run, scope=scope, project_root=project_root
            )


@given(prefix=_TEXT_FRAGMENT, suffix=_TEXT_FRAGMENT, binary=_BINARY_TEXT)
def test_render_pi_extension_replaces_exact_placeholder_property(
    prefix: str, suffix: str, binary: str
) -> None:
    template = f"{prefix}{_PI_PLACEHOLDER}{suffix}"
    rendered = slopgate.installer._pi.render_pi_extension(template, binary)
    expected = (
        f"{prefix}"
        f"{json.dumps(slopgate.installer._shared.base_invocation(binary))}"
        f"{suffix}"
    )
    assert rendered == expected, (
        "render_pi_extension must replace only the argv placeholder"
    )


@given(scope=_INSTALL_SCOPE, dry_run=strategies.booleans())
def test_install_pi_scope_status_property(scope: str, dry_run: bool) -> None:
    assert install_status_for_scope(scope, dry_run) == 0, (
        "install_pi should accept every normalized scope in dry and write modes"
    )


@given(scope=_INSTALL_SCOPE, dry_run=strategies.booleans())
def test_uninstall_pi_scope_status_property(scope: str, dry_run: bool) -> None:
    assert uninstall_status_for_scope(scope, dry_run) == 0, (
        "uninstall_pi should accept every normalized scope in dry and write modes"
    )


@given(prefix=_TEXT_FRAGMENT, suffix=_TEXT_FRAGMENT, markers=_PI_MARKER_SUBSET)
def test_pi_extension_ownership_requires_every_marker_property(
    prefix: str, suffix: str, markers: frozenset[str]
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        extension_path = Path(temp_dir) / "index.ts"
        content = "\n".join((prefix, *sorted(markers), suffix))
        extension_path.write_text(content, encoding="utf-8")

        result = slopgate.installer._pi.pi_extension_has_owned_slopgate(extension_path)

        assert result is (
            markers == frozenset(slopgate.installer._pi.PI_OWNERSHIP_MARKERS)
        ), "Pi ownership must require every canonical extension marker"
