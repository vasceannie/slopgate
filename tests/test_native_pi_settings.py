from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer.native.model import LegacyRefusal, NativeRequest
from slopgate.installer.native.pi.commands import pi_scope_command, run_pi_command
from slopgate.installer.native.pi.identity import PI_EXECUTABLE
from slopgate.installer.native.pi.install import install_pi_package
from slopgate.installer.native.pi.legacy import (
    is_owned_pi_package,
    pi_agent_dir,
    pi_has_owned_extension_entry,
    pi_project_extension_path,
    pi_user_extension_path,
)
from slopgate.installer.native.pi.package import PI_PACKAGE_NAME
from slopgate.installer.native.pi.settings import (
    package_entries,
    project_settings_path,
    registered_entry,
    resolve_source,
    settings_directory,
    settings_path,
    user_settings_path,
)
from slopgate.installer.native.pi.uninstall import uninstall_pi_package
from tests.native.pi_support import PiHarness, make_harness

PROPERTY_EXAMPLES = 20
TEST_BINARY = "slopgate-pi-property-test"
_PATH_COMPONENT = strategies.text(
    alphabet=strategies.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=10,
)
_SOURCE_VALUE = strategies.text(
    alphabet=strategies.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=24,
)

_SCOPE_VALUES = strategies.sampled_from((INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT))
_INSTALL_CASES = strategies.tuples(_SCOPE_VALUES, _SOURCE_VALUE)
_UNINSTALL_CASES = _SCOPE_VALUES


@contextmanager
def _property_sandbox(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[tuple[Path, pytest.MonkeyPatch]]:
    root = tmp_path_factory.mktemp("pi-native-property")
    with pytest.MonkeyPatch.context() as monkeypatch:
        yield root, monkeypatch


def _write_user_package_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> Path:
    agent_dir = tmp_path / "agent"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
    settings_file = tmp_path / "settings.json"
    raw_entry: dict[str, object] = {"source": source, "extensions": ["./index.ts"]}
    settings_file.write_text(json.dumps({"packages": [raw_entry]}), encoding="utf-8")
    return settings_file


def _write_project_package_settings(tmp_path: Path, source: str) -> tuple[Path, Path]:
    root = tmp_path / "project"
    settings_file = project_settings_path(root)
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(json.dumps({"packages": [source]}), encoding="utf-8")
    expected = resolve_source(settings_directory(INSTALL_SCOPE_PROJECT, root), source)
    return root, expected


def _pi_install_observation(
    harness: PiHarness, scope: str
) -> tuple[bool, bool, object, bool, bool]:
    entry = registered_entry(scope, harness.project, harness.package_root)
    manifest = json.loads(
        (harness.package_root / "package.json").read_text(encoding="utf-8")
    )
    version = manifest.get("version")
    return (
        entry is not None and entry.resolved == harness.package_root.resolve(),
        entry is not None and entry.filtered,
        manifest.get("name"),
        isinstance(version, str) and bool(version),
        harness.package_root.is_dir(),
    )


def _install_pi_request(harness: PiHarness, scope: str, binary: str) -> NativeRequest:
    request = NativeRequest(False, (scope,), harness.project)
    status = install_pi_package(request, binary)
    assert status == 0, "Pi install precondition should register the scoped package"
    return request


def _pi_uninstall_observation(harness: PiHarness, scope: str) -> tuple[bool, bool]:
    return (
        registered_entry(scope, harness.project, harness.package_root) is None,
        harness.package_root.is_dir(),
    )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(segment=_PATH_COMPONENT)
def test_settings_path_project_scope_is_root_relative(
    tmp_path_factory: pytest.TempPathFactory, segment: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, _):
        root = tmp_path / segment
        actual = settings_path(INSTALL_SCOPE_PROJECT, root)

        assert actual == root / ".pi" / "settings.json", (
            "project Pi settings should always be rooted below the selected project"
        )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(segment=_PATH_COMPONENT)
def test_settings_path_user_scope_uses_active_agent_directory(
    tmp_path_factory: pytest.TempPathFactory, segment: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, monkeypatch):
        agent_dir = tmp_path / segment
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
        actual = settings_path(INSTALL_SCOPE_USER, tmp_path)

        assert actual == agent_dir / "settings.json", (
            "user settings should follow the active PI_CODING_AGENT_DIR rather than project state"
        )


def test_settings_path_rejects_implicit_both_scope(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported Pi scope"):
        settings_path("both", tmp_path)


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(source=_SOURCE_VALUE)
def test_package_entries_preserve_source_and_filter_state(
    tmp_path_factory: pytest.TempPathFactory, source: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, monkeypatch):
        settings_file = _write_user_package_settings(tmp_path, monkeypatch, source)
        entries = package_entries(settings_file, INSTALL_SCOPE_USER, tmp_path)

        assert len(entries) == 1, "one configured Pi package should produce one entry"
        assert (entries[0].source, entries[0].filtered) == (source, True), (
            "Pi package parsing should preserve source text and resource filters"
        )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(source=_SOURCE_VALUE)
def test_registered_entry_resolves_against_project_settings_directory(
    tmp_path_factory: pytest.TempPathFactory, source: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, _):
        root, expected = _write_project_package_settings(tmp_path, source)
        entry = registered_entry(INSTALL_SCOPE_PROJECT, root, expected)

        assert entry is not None, "the matching project package should be registered"
        assert entry.resolved == expected, (
            "relative package sources should resolve from the selected project settings file"
        )


def test_settings_and_legacy_helpers_keep_native_paths_disjoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_dir = tmp_path / "agent"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
    project = tmp_path / "project"
    observed = (
        pi_agent_dir(),
        user_settings_path(),
        project_settings_path(project),
        settings_directory(INSTALL_SCOPE_PROJECT, project),
        pi_user_extension_path(),
        pi_project_extension_path(project),
    )

    assert observed == (
        agent_dir,
        agent_dir / "settings.json",
        project / ".pi" / "settings.json",
        project / ".pi",
        agent_dir / "extensions" / PI_PACKAGE_NAME / "index.ts",
        project / ".pi" / "extensions" / PI_PACKAGE_NAME / "index.ts",
    ), "Pi settings and legacy extension paths should remain scope-separated"


def test_legacy_pi_helpers_recognize_owned_package_markers(tmp_path: Path) -> None:
    package = tmp_path / PI_PACKAGE_NAME
    package.mkdir()
    (package / "index.js").write_text(
        f"// {PI_PACKAGE_NAME}\nslopgate handle --platform pi\n",
        encoding="utf-8",
    )
    manifest = json.dumps({"peerDependencies": {"@earendil-works/pi-tui": "*"}})

    assert is_owned_pi_package(manifest), (
        "legacy Pi manifests with the owned peer marker should be recognized"
    )
    assert pi_has_owned_extension_entry(package), (
        "legacy Pi entry files with the owned package marker should be recognized"
    )


def test_missing_user_settings_have_no_registered_packages(tmp_path: Path) -> None:
    entries = package_entries(
        tmp_path / "absent-settings.json", INSTALL_SCOPE_USER, tmp_path
    )

    assert entries == (), "missing Pi settings should represent an empty package list"


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(case=_INSTALL_CASES)
def test_install_pi_package_property_for_each_native_scope(
    tmp_path_factory: pytest.TempPathFactory, case: tuple[str, str]
) -> None:
    scope, binary = case
    with _property_sandbox(tmp_path_factory) as (tmp_path, monkeypatch):
        harness = make_harness(tmp_path, monkeypatch)
        request = NativeRequest(False, (scope,), harness.project)
        status = install_pi_package(request, binary)
        assert status == 0, (
            "Pi native install should register a valid generated package"
        )
        observed = _pi_install_observation(harness, scope)

        assert observed == (True, False, PI_PACKAGE_NAME, True, True), (
            "Pi installation should register the active source with its generated package version"
        )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(scope=_UNINSTALL_CASES)
def test_uninstall_pi_package_property_removes_selected_registration(
    tmp_path_factory: pytest.TempPathFactory, scope: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, monkeypatch):
        harness = make_harness(tmp_path, monkeypatch)
        request = _install_pi_request(harness, scope, TEST_BINARY)
        status = uninstall_pi_package(request)
        assert status == 0, "Pi native uninstall should remove the selected scope"
        observed = _pi_uninstall_observation(harness, scope)

        assert observed == (True, True), (
            "uninstall should remove only registration state and retain its reusable package"
        )


def test_package_entries_refuse_malformed_filter_entry(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"packages": [{"extensions": ["./index.ts"]}]}),
        encoding="utf-8",
    )

    with pytest.raises(LegacyRefusal, match="malformed Pi package entry"):
        package_entries(settings_file, INSTALL_SCOPE_PROJECT, tmp_path)


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(scope=_SCOPE_VALUES, component=_SOURCE_VALUE)
def test_pi_scope_command_property_preserves_source_and_scope_flag(
    tmp_path_factory: pytest.TempPathFactory, scope: str, component: str
) -> None:
    with _property_sandbox(tmp_path_factory) as (tmp_path, _):
        source = tmp_path / f"package with spaces {component}"
        expected_flags = {
            INSTALL_SCOPE_USER: [],
            INSTALL_SCOPE_PROJECT: ["-l"],
        }[scope]

        assert pi_scope_command("install", source, scope) == [
            PI_EXECUTABLE,
            "install",
            *expected_flags,
            str(source),
        ], "Pi scope commands should preserve the exact source and project-only flag"


def test_run_pi_command_uses_request_root_and_active_agent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    request = NativeRequest(False, (INSTALL_SCOPE_USER,), harness.project)

    output = run_pi_command([PI_EXECUTABLE, "list"], request)
    calls = harness.fake.calls()
    observed = (output.strip(), calls[-1]["cwd"], calls[-1]["scope"])

    assert observed == (
        "No packages installed.",
        str(harness.project),
        INSTALL_SCOPE_USER,
    ), (
        "Pi commands should execute in the requested project with its active user settings"
    )
