from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.installer._shared import ContainedWrite
from slopgate.resources import resource_path

TEST_BINARY = str(Path.cwd() / "slopgate-test-bin")
MANIFEST_PAYLOAD = {
    "name": "omp-slopgate",
    "private": True,
    "type": "module",
    "omp": {"extensions": ["./index.ts"]},
    "peerDependencies": {
        "@oh-my-pi/pi-coding-agent": "*",
        "@oh-my-pi/pi-tui": "*",
    },
}
MANIFEST_BYTES = (json.dumps(MANIFEST_PAYLOAD, indent=2) + "\n").encode()


@dataclass(frozen=True, slots=True)
class OwnedSiteSeed:
    index_bytes: bytes
    manifest_bytes: bytes
    index_mode: int = 0o640
    manifest_mode: int = 0o600

    @classmethod
    def from_paths(cls, index_path: Path, manifest_path: Path) -> OwnedSiteSeed:
        return cls(
            index_bytes=index_path.read_bytes(),
            manifest_bytes=manifest_path.read_bytes(),
            index_mode=stat.S_IMODE(index_path.stat().st_mode),
            manifest_mode=stat.S_IMODE(manifest_path.stat().st_mode),
        )


@dataclass(frozen=True, slots=True)
class CrossSiteFailureScenario:
    project_root: Path
    project_index: Path
    user_index: Path
    user_manifest: Path
    expected_user: OwnedSiteSeed


def patch_install(
    monkeypatch: pytest.MonkeyPatch, home: Path, binary: str = TEST_BINARY
) -> None:
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: binary)


def patch_unreadable_artifact(
    monkeypatch: pytest.MonkeyPatch,
    artifact: Path,
) -> None:
    original_read_text = Path.read_text

    def unreadable_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == artifact:
            raise OSError(f"unreadable artifact: {path}")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", unreadable_read_text)


def site_paths(agent_dir: Path) -> tuple[Path, Path]:
    package_dir = agent_dir / "extensions" / "omp-slopgate"
    return package_dir / "index.ts", package_dir / "package.json"


def owned_index(binary: str) -> bytes:
    template = resource_path("omp_extension.ts").read_text(encoding="utf-8")
    return slopgate.installer._omp.render_omp_extension(template, binary).encode()


def write_owned_site(agent_dir: Path, seed: OwnedSiteSeed) -> tuple[Path, Path]:
    index_path, manifest_path = site_paths(agent_dir)
    index_path.parent.mkdir(parents=True)
    index_path.write_bytes(seed.index_bytes)
    manifest_path.write_bytes(seed.manifest_bytes)
    index_path.chmod(seed.index_mode)
    manifest_path.chmod(seed.manifest_mode)
    return index_path, manifest_path


def prepare_cross_site_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> CrossSiteFailureScenario:
    home = tmp_path / "home"
    project_root = tmp_path / "repo"
    project_root.mkdir()
    patch_install(monkeypatch, home)
    expected_user = OwnedSiteSeed(
        b"// retained prefix\n" + owned_index(str(tmp_path / "old-bin")),
        json.dumps(MANIFEST_PAYLOAD, separators=(",", ":")).encode(),
    )
    user_index, user_manifest = write_owned_site(
        home / ".omp" / "agent", expected_user
    )
    project_index, project_manifest = site_paths(project_root / ".omp")
    fail_manifest_write(monkeypatch, project_manifest)
    return CrossSiteFailureScenario(
        project_root=project_root,
        project_index=project_index,
        user_index=user_index,
        user_manifest=user_manifest,
        expected_user=expected_user,
    )


def transaction_residue(root: Path) -> tuple[Path, ...]:
    return tuple(root.rglob("*.slopgate-bak-*")) + tuple(
        root.rglob(".slopgate-write-*.tmp")
    )


def fail_manifest_write(
    monkeypatch: pytest.MonkeyPatch, manifest_path: Path
) -> None:
    original = slopgate.installer._omp.write_contained_text

    def fail_manifest(target: Path, content: str, write: ContainedWrite) -> Path:
        if target == manifest_path:
            raise OSError("manifest write failed")
        return original(target, content, write)

    monkeypatch.setattr(slopgate.installer._omp, "write_contained_text", fail_manifest)
