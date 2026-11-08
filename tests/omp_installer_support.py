from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._omp_support import MANIFEST_TEXT
from slopgate.resources import resource_path
from tests.native.environment import isolate_native_data_dirs
from tests.native.omp_fake import OMP_PLUGIN_ID, write_fake_omp

TEST_BINARY = "slopgate-test-bin"
REFRESHED_BINARY = "slopgate-refreshed-bin"


class _EnvironmentPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...

    def setenv(self, name: str, value: str) -> None: ...


@dataclass(frozen=True, slots=True)
class OmpSandbox:
    home: Path
    agent_dir: Path
    project_root: Path
    bin_dir: Path
    launcher: Path
    state_path: Path


@dataclass(frozen=True, slots=True)
class _EnvironmentPaths:
    home: Path
    agent_dir: Path
    xdg_root: Path
    state_path: Path
    bin_dir: Path


def prepare_omp_sandbox(
    monkeypatch: _EnvironmentPatch, tmp_path: Path, binary: str = TEST_BINARY
) -> OmpSandbox:
    isolate_native_data_dirs(monkeypatch, tmp_path)
    paths = _EnvironmentPaths(
        home=tmp_path / "home",
        agent_dir=tmp_path / "home" / ".omp" / "agent",
        xdg_root=tmp_path / "xdg",
        state_path=tmp_path / "omp-state.json",
        bin_dir=tmp_path / "bin",
    )
    project_root = tmp_path / "project with space"
    project_root.mkdir()
    _set_environment(monkeypatch, paths)
    launcher = write_fake_omp(paths.bin_dir)
    monkeypatch.setattr(Path, "home", lambda: paths.home)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: binary)
    return OmpSandbox(
        paths.home,
        paths.agent_dir,
        project_root,
        paths.bin_dir,
        launcher,
        paths.state_path,
    )


def _set_environment(monkeypatch: _EnvironmentPatch, paths: _EnvironmentPaths) -> None:
    monkeypatch.setenv("HOME", str(paths.home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(paths.agent_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(paths.xdg_root / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(paths.xdg_root / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(paths.xdg_root / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(paths.xdg_root / "cache"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(paths.xdg_root / "run"))
    monkeypatch.setenv("FAKE_OMP_STATE", str(paths.state_path))
    current_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", str(paths.bin_dir) + os.pathsep + current_path)


def legacy_paths(sandbox: OmpSandbox, scope: str) -> tuple[Path, Path]:
    if scope == INSTALL_SCOPE_USER:
        index = sandbox.agent_dir / "extensions" / "omp-slopgate" / "index.ts"
    elif scope == INSTALL_SCOPE_PROJECT:
        index = (
            sandbox.project_root / ".omp" / "extensions" / "omp-slopgate" / "index.ts"
        )
    else:
        raise ValueError(f"unsupported legacy OMP scope: {scope}")
    return index, index.with_name("package.json")


def owned_index(binary: str = TEST_BINARY) -> bytes:
    template = resource_path("omp_extension.ts").read_text(encoding="utf-8")
    return slopgate.installer._omp.render_omp_extension(template, binary).encode()


def seed_legacy(sandbox: OmpSandbox, scope: str) -> tuple[Path, Path]:
    index, manifest = legacy_paths(sandbox, scope)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(owned_index())
    manifest.write_text(MANIFEST_TEXT, encoding="utf-8")
    index.chmod(0o640)
    manifest.chmod(0o600)
    return index, manifest


def native_inventory(sandbox: OmpSandbox, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        [str(sandbox.launcher), "plugin", "list", "--json"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return cast(dict[str, object], json.loads(completed.stdout))


def entries_for_scope(
    inventory: dict[str, object], scope: str
) -> list[dict[str, object]]:
    plugins = cast(list[dict[str, object]], inventory["marketplace"])
    return [
        entry
        for plugin in plugins
        if plugin.get("id") == OMP_PLUGIN_ID
        for entry in cast(list[dict[str, object]], plugin["entries"])
        if entry.get("scope") == scope
    ]


def seed_marketplace_collision(sandbox: OmpSandbox, source: Path) -> None:
    state: dict[str, object] = {
        "marketplaces": {"slopgate-runtime": str(source.resolve())},
        "registrations": [],
        "calls": [],
    }
    sandbox.state_path.write_text(json.dumps(state), encoding="utf-8")


def seed_unrelated_registration(sandbox: OmpSandbox) -> None:
    state: dict[str, object] = {
        "marketplaces": {},
        "registrations": [
            {
                "id": "unrelated-package@other-marketplace",
                "scope": "project",
                "project": str(sandbox.project_root.resolve()),
                "version": "1.0.0",
                "enabled": True,
            }
        ],
        "calls": [],
    }
    sandbox.state_path.write_text(json.dumps(state), encoding="utf-8")


def set_fake_failure(
    monkeypatch: _EnvironmentPatch, command: str, *, after_mutation: bool = False
) -> None:
    monkeypatch.setenv("FAKE_OMP_FAIL_ON", command)
    mutation_mode = "1" if after_mutation else "0"
    monkeypatch.setenv("FAKE_OMP_FAIL_AFTER_MUTATION", mutation_mode)


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_dir():
            digest.update(b"directory")
        elif path.is_file():
            digest.update(b"file")
            digest.update(path.read_bytes())
    return digest.hexdigest()
