from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .native import (
    CLAUDE_ID,
    OMP_ID,
    PI_NAME,
    claude_marketplace_source,
    claude_registration,
    omp_marketplace_source,
    omp_registration,
    package_root,
    pi_list,
    pi_package_source,
    pi_settings_path,
)
from .sandbox import Sandbox, SmokeFailure

SCOPES = ("user", "project")


def _read_object(path: Path, label: str) -> dict[str, object]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SmokeFailure(f"{label} is not a JSON object: {path}")
    return cast(dict[str, object], parsed)


def _catalog_payload(sandbox: Sandbox, host: str) -> tuple[Path, dict[str, object]]:
    marketplace = package_root(sandbox, host)
    catalog_path = (
        marketplace / ".omp-plugin" / "marketplace.json"
        if host == "omp"
        else marketplace / ".claude-plugin" / "marketplace.json"
    )
    catalog = _read_object(catalog_path, f"{host} staged marketplace")
    entries = catalog.get("plugins")
    if not isinstance(entries, list):
        raise SmokeFailure(f"{host} staged marketplace has no plugin list")

    plugin_name = (
        OMP_ID.split("@", maxsplit=1)[0]
        if host == "omp"
        else CLAUDE_ID.split("@", maxsplit=1)[0]
    )
    matches: list[dict[str, object]] = []
    for raw_entry in cast(list[object], entries):
        if not isinstance(raw_entry, dict):
            raise SmokeFailure(f"{host} marketplace contains a malformed plugin")
        entry = cast(dict[str, object], raw_entry)
        if entry.get("name") == plugin_name:
            matches.append(entry)
    if len(matches) != 1:
        raise SmokeFailure(
            f"{host} marketplace must contain exactly one {plugin_name} entry"
        )
    source = matches[0].get("source")
    if not isinstance(source, str):
        raise SmokeFailure(f"{host} marketplace entry has no local source")
    expected_prefix = f"./plugins/{plugin_name}/"
    if not source.startswith(expected_prefix):
        raise SmokeFailure(
            f"{host} marketplace source is not the owned snapshot: {source}"
        )
    payload = (marketplace / source).resolve()
    if not payload.is_dir() or marketplace.resolve() not in payload.parents:
        raise SmokeFailure(
            f"{host} marketplace source escaped its staging root: {source}"
        )
    return payload, matches[0]


def staged_payload_path(sandbox: Sandbox, host: str) -> Path:
    return _catalog_payload(sandbox, host)[0]


def _assert_omp(sandbox: Sandbox, scope: str) -> str:
    root = package_root(sandbox, "omp")
    source = omp_marketplace_source(sandbox)
    if source != root.resolve():
        raise SmokeFailure(
            f"OMP marketplace source mismatch: {source} != {root.resolve()}"
        )
    payload, catalog_entry = _catalog_payload(sandbox, "omp")
    registration = omp_registration(sandbox, scope)
    if registration is None:
        raise SmokeFailure(
            f"OMP inventory is missing {scope} registration for {OMP_ID}"
        )
    install_path = registration.get("installPath")
    if not isinstance(install_path, str):
        raise SmokeFailure(f"OMP {scope} registration has no installPath")
    installed = Path(install_path).resolve()
    if (
        sandbox.root.resolve() not in installed.parents
        or not (installed / "index.ts").is_file()
    ):
        raise SmokeFailure(
            f"OMP {scope} native install path is not sandboxed/loadable: {installed}"
        )
    staged_manifest = _read_object(
        payload / "package.json", "OMP staged package manifest"
    )
    installed_manifest = _read_object(
        installed / "package.json", "OMP registered package manifest"
    )
    version = staged_manifest.get("version")
    if not isinstance(version, str) or installed_manifest.get("version") != version:
        raise SmokeFailure(
            f"OMP {scope} installed version differs from its marketplace payload"
        )
    if (
        registration.get("version") != version
        or catalog_entry.get("version") != version
    ):
        raise SmokeFailure(
            f"OMP {scope} inventory/catalog version differs from package version"
        )
    if registration.get("enabled") is False:
        raise SmokeFailure(f"OMP {scope} registration unexpectedly starts disabled")
    return (
        f"OMP {scope}: id={OMP_ID}, marketplace={root.resolve()}, "
        f"install_path={installed}, version={version}, "
        f"enabled={registration.get('enabled', True)}"
    )


def _assert_pi(sandbox: Sandbox, scope: str) -> str:
    source = pi_package_source(sandbox, scope)
    expected = package_root(sandbox, "pi").resolve()
    if source is None:
        raise SmokeFailure(f"Pi {scope} settings are missing package source {expected}")
    source_text = source.get("source")
    if not isinstance(source_text, str):
        raise SmokeFailure(f"Pi {scope} package source is malformed")
    actual = Path(source_text).expanduser()
    if not actual.is_absolute():
        actual = pi_settings_path(sandbox, scope).parent / actual
    if actual.resolve() != expected:
        raise SmokeFailure(
            f"Pi {scope} package source mismatch: {actual} != {expected}"
        )
    manifest = _read_object(expected / "package.json", "Pi native package manifest")
    if manifest.get("name") != PI_NAME or manifest.get("private") is not True:
        raise SmokeFailure(
            f"Pi staged package has the wrong native identity: {manifest}"
        )
    output = pi_list(sandbox)
    if str(expected) not in output:
        raise SmokeFailure(
            f"Pi list omitted the exact package source {expected}: {output}"
        )
    filters = source.get("extensions")
    if filters is not None and (
        not isinstance(filters, list)
        or not {"index.ts", "./index.ts"}.intersection(cast(list[str], filters))
    ):
        raise SmokeFailure(
            f"Pi {scope} package entry is not enabled for index.ts: {source}"
        )
    version = manifest.get("version")
    if not isinstance(version, str):
        raise SmokeFailure("Pi package manifest has no version")
    return f"Pi {scope}: source={expected}, version={version}, extensions={filters!r}"


def _claude_staged_version(sandbox: Sandbox) -> tuple[Path, str]:
    root = package_root(sandbox, "claude")
    source = claude_marketplace_source(sandbox)
    if source != root.resolve():
        raise SmokeFailure(
            f"Claude marketplace source mismatch: {source} != {root.resolve()}"
        )
    payload, catalog_entry = _catalog_payload(sandbox, "claude")
    manifest = _read_object(
        payload / ".claude-plugin" / "plugin.json", "Claude staged plugin manifest"
    )
    version = manifest.get("version")
    if not isinstance(version, str) or catalog_entry.get("version") not in (
        None,
        version,
    ):
        raise SmokeFailure("Claude catalog and staged plugin versions do not agree")
    return payload, version


def _assert_claude_install_path(
    sandbox: Sandbox, registration: dict[str, object]
) -> None:
    install_path = registration.get("installPath")
    if not isinstance(install_path, str):
        raise SmokeFailure("Claude registration has no installPath")
    installed = Path(install_path).resolve()
    if sandbox.root.resolve() not in installed.parents or not installed.exists():
        raise SmokeFailure(f"Claude native install path is not sandboxed: {installed}")


def _assert_claude_source(registration: dict[str, object], payload: Path) -> None:
    read_from = registration.get("readFromFolder")
    if not isinstance(read_from, str) or Path(read_from).resolve() != payload.resolve():
        raise SmokeFailure(
            f"Claude registration source differs from its staged marketplace: {read_from!r}"
        )


def _assert_claude_project(
    sandbox: Sandbox, scope: str, registration: dict[str, object]
) -> None:
    if scope != "project":
        return
    project_path = registration.get("projectPath")
    if (
        not isinstance(project_path, str)
        or Path(project_path).resolve() != sandbox.project.resolve()
    ):
        raise SmokeFailure(
            f"Claude project registration targets the wrong root: {project_path!r}"
        )


def _assert_claude_enabled(registration: dict[str, object]) -> object:
    enabled = registration.get("enabled", registration.get("projectEnabled", True))
    if enabled is False:
        raise SmokeFailure("Claude native registration unexpectedly starts disabled")
    return enabled


def _assert_claude_registration(
    sandbox: Sandbox, scope: str, payload: Path, version: str
) -> dict[str, object]:
    registration = claude_registration(sandbox, scope)
    if registration is None:
        raise SmokeFailure(
            f"Claude inventory is missing {scope} registration for {CLAUDE_ID}"
        )
    if registration.get("version") != version:
        raise SmokeFailure(
            f"Claude {scope} inventory version differs from its staged plugin"
        )
    _assert_claude_install_path(sandbox, registration)
    _assert_claude_source(registration, payload)
    _assert_claude_project(sandbox, scope, registration)
    _assert_claude_enabled(registration)
    return registration


def _assert_claude(sandbox: Sandbox, scope: str) -> str:
    payload, version = _claude_staged_version(sandbox)
    registration = _assert_claude_registration(sandbox, scope, payload, version)
    enabled = registration.get("enabled", registration.get("projectEnabled", True))
    source = cast(str, registration.get("readFromFolder"))
    install_path = cast(str, registration.get("installPath"))
    return (
        f"Claude {scope}: id={CLAUDE_ID}, source={source}, "
        f"install_path={install_path}, version={version}, enabled={enabled}"
    )


def assert_registrations(sandbox: Sandbox) -> list[str]:
    receipts: list[str] = []
    for scope in SCOPES:
        receipts.append(_assert_omp(sandbox, scope))
        receipts.append(_assert_pi(sandbox, scope))
        receipts.append(_assert_claude(sandbox, scope))
    return receipts
