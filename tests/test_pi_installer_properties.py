from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies

import slopgate.installer
import slopgate.installer._pi
import slopgate.installer._shared
from slopgate.installer.native.model import make_request
from slopgate.installer.native.pi.legacy import pi_agent_dir, pi_template_path
from slopgate.installer.native.pi.package import pi_manifest, pi_payload
from slopgate.installer.native.pi.settings import resolve_source

_PI_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_TEXT_FRAGMENT = strategies.text(alphabet=list("abcXYZ012 _-."), max_size=20)
_BINARY_TEXT = strategies.text(alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20)
_INSTALL_SCOPE = strategies.sampled_from(["user", "project", "both"])
_PI_MARKER_SUBSET = strategies.frozensets(
    strategies.sampled_from(slopgate.installer._pi.PI_OWNERSHIP_MARKERS)
)
_RELATIVE_SOURCE_PARTS = strategies.lists(
    strategies.sampled_from(["packages", "shared", "pkg with spaces", ".."]),
    min_size=1,
    max_size=4,
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
        "Pi rendering must replace only the binary argv placeholder"
    )


def _attempt_legacy_pi_uninstall(
    temp_dir: str, prefix: str, suffix: str, markers: frozenset[str]
) -> tuple[int, bool]:
    project = Path(temp_dir)
    extension = project / ".pi" / "extensions" / "pi-slopgate"
    extension.mkdir(parents=True)
    path = extension / "index.ts"
    path.write_text("\n".join((prefix, *sorted(markers), suffix)), encoding="utf-8")
    with patch.object(Path, "home", return_value=project):
        status = slopgate.installer.uninstall_platform(
            "pi", install_scope="project", project_root=project
        )
    return status, path.exists()


@given(prefix=_TEXT_FRAGMENT, suffix=_TEXT_FRAGMENT, markers=_PI_MARKER_SUBSET)
def test_pi_legacy_ownership_requires_every_canonical_marker(
    prefix: str, suffix: str, markers: frozenset[str]
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        status, entry_exists = _attempt_legacy_pi_uninstall(
            temp_dir, prefix, suffix, markers
        )
    expected_owned = markers == frozenset(slopgate.installer._pi.PI_OWNERSHIP_MARKERS)
    expected_status = 0 if expected_owned else 1
    assert (status, entry_exists) == (expected_status, not expected_owned), (
        "Pi uninstall should remove only legacy entries with every canonical marker"
    )


@given(scope=_INSTALL_SCOPE)
def test_native_request_expands_only_explicit_pi_scopes(scope: str) -> None:
    request = make_request(scope, Path.cwd(), dry_run=True)
    expected = ("user", "project") if scope == "both" else (scope,)
    assert request.scopes == expected, (
        "Pi scope expansion must preserve user-then-project order"
    )
    assert "both" not in request.scopes, "native Pi commands must never receive both"


@given(version=_TEXT_FRAGMENT)
def test_pi_manifest_uses_native_identity_and_host_provided_peers(version: str) -> None:
    manifest = pi_manifest(version)
    assert manifest["name"] == "pi-slopgate", "Pi package identity must remain stable"
    assert manifest["version"] == version, (
        "staged manifest must embed its planned version"
    )
    assert manifest["private"] is True, "native package must remain private"
    assert manifest["type"] == "module", "Pi package must use ESM"
    assert manifest["keywords"] == ["pi-package"], (
        "Pi native package keyword is required"
    )
    assert manifest["pi"] == {"extensions": ["./index.ts"]}, "Pi must load index.ts"
    assert manifest["peerDependencies"] == {
        "@earendil-works/pi-coding-agent": "*",
        "@earendil-works/pi-tui": "*",
    }, "Pi host peer dependencies must be declared without installing them"
    assert "dependencies" not in manifest, (
        "the package must not add runtime dependencies"
    )


@given(version=_TEXT_FRAGMENT)
def test_pi_payload_contains_only_manifest_and_rendered_entry(version: str) -> None:
    template = pi_template_path().read_text(encoding="utf-8")
    files = pi_payload(template, "/tmp/slopgate")(version)
    manifest = json.loads(files["package.json"])
    assert set(files) == {"package.json", "index.ts"}, "Pi must not stage config.json"
    assert manifest["version"] == version, (
        "payload and embedded manifest versions must agree"
    )
    assert "__SLOPGATE_BIN__" not in files["index.ts"], (
        "rendered extension must bind argv"
    )
    assert "/tmp/slopgate" in files["index.ts"], (
        "rendered extension must use the resolved binary"
    )


@given(parts=_RELATIVE_SOURCE_PARTS)
def test_relative_native_sources_resolve_against_settings_directory(
    parts: list[str],
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        settings_dir = Path(temp_dir) / "agent"
        relative_source = str(Path(*parts))
        expected = (settings_dir / relative_source).resolve()
        assert resolve_source(settings_dir, relative_source) == expected, (
            "relative Pi package sources must resolve from the settings directory"
        )


def test_user_agent_directory_honors_absolute_environment_value(tmp_path: Path) -> None:
    configured = tmp_path / "custom-agent"
    with patch.dict(os.environ, {"PI_CODING_AGENT_DIR": str(configured)}):
        assert pi_agent_dir() == configured.resolve(), (
            "absolute PI_CODING_AGENT_DIR must select Pi's user state root"
        )
