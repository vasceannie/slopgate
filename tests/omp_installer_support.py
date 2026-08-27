from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.installer._shared import ContainedWrite

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


@dataclass(frozen=True, slots=True)
class OwnedSiteSeed:
    index_bytes: bytes
    manifest_bytes: bytes
    index_mode: int = 0o640
    manifest_mode: int = 0o600


def patch_install(
    monkeypatch: pytest.MonkeyPatch, home: Path, binary: str = TEST_BINARY
) -> None:
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: binary)


def site_paths(agent_dir: Path) -> tuple[Path, Path]:
    package_dir = agent_dir / "extensions" / "omp-slopgate"
    return package_dir / "index.ts", package_dir / "package.json"


def owned_index(binary: str) -> bytes:
    template = slopgate.installer._omp._omp_template_text()
    assert template is not None, "the packaged OMP template must exist"
    return slopgate.installer._omp.render_omp_extension(template, binary).encode()


def write_owned_site(agent_dir: Path, seed: OwnedSiteSeed) -> tuple[Path, Path]:
    index_path, manifest_path = site_paths(agent_dir)
    index_path.parent.mkdir(parents=True)
    index_path.write_bytes(seed.index_bytes)
    manifest_path.write_bytes(seed.manifest_bytes)
    index_path.chmod(seed.index_mode)
    manifest_path.chmod(seed.manifest_mode)
    return index_path, manifest_path


def fail_manifest_write(
    monkeypatch: pytest.MonkeyPatch, manifest_path: Path
) -> None:
    original = slopgate.installer._omp.write_contained_text

    def fail_manifest(target: Path, content: str, write: ContainedWrite) -> Path:
        if target == manifest_path:
            raise OSError("manifest write failed")
        return original(target, content, write)

    monkeypatch.setattr(slopgate.installer._omp, "write_contained_text", fail_manifest)
