"""Hermetic fake OMP/Claude/Pi managers for installer and suite tests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import slopgate.installer._shared
import slopgate.installer.native.entry
import slopgate.installer.native.hook_install
import tests.native.claude_fake
import tests.native.omp_fake
from slopgate.installer.native.packages import native_host_root
from tests.native.environment import isolate_native_data_dirs
from tests.native.pi_fake import FakePi

HOST_EXECUTABLES = ("claude", "omp", "pi")
_CLAUDE_MUTATIONS = {"install", "uninstall", "disable", "enable"}
_CLAUDE_MARKETPLACE_MUTATIONS = {"add", "update", "remove"}
_PI_MUTATIONS = {"install", "remove", "uninstall"}
_FAILURE_ENVIRONMENT = (
    "FAKE_OMP_FAIL_ON",
    "FAKE_OMP_FAIL_AFTER_MUTATION",
    "FAKE_CLAUDE_FAIL",
    "FAKE_CLAUDE_FAIL_AFTER",
    "FAKE_CLAUDE_RELATIVE_SOURCE",
    "CLAUDE_CODE_PLUGIN_DIRS",
)


class _TestPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...

    def setenv(self, name: str, value: str) -> None: ...

    def delenv(self, name: str, raising: bool = True) -> None: ...


@dataclass(frozen=True, slots=True)
class _HostPaths:
    home: Path
    project: Path
    bin_dir: Path
    agent_dir: Path
    state_dir: Path
    pi_root: Path
    xdg_root: Path


@dataclass(slots=True)
class FakeHosts:
    """Sandbox paths and fake manager state recorded below them."""

    home: Path
    bin_dir: Path
    project: Path
    pi: FakePi
    omp_state_path: Path
    claude_state_path: Path
    claude_log_path: Path

    @property
    def staging_root(self) -> Path:
        """Slopgate's shared native staging area within this sandbox."""
        return native_host_root("pi").parent

    def omp_calls(self) -> list[list[str]]:
        """Mutating OMP calls (its fake omits read-only calls from the log)."""
        state = tests.native.omp_fake.read_fake_state(self.omp_state_path)
        calls = cast(list[list[object]], state.get("calls", []))
        return [[str(argument) for argument in call] for call in calls]

    def claude_calls(self) -> list[list[str]]:
        """Every fake Claude invocation, including read-only inventory calls."""
        if not self.claude_log_path.exists():
            return []
        lines = self.claude_log_path.read_text(encoding="utf-8").splitlines()
        return [
            [str(argument) for argument in cast(list[object], json.loads(line))]
            for line in lines
            if line
        ]

    def pi_calls(self) -> list[dict[str, object]]:
        """Every Pi call record (argv, cwd and scope)."""
        return self.pi.calls()

    def mutating_calls(self) -> list[str]:
        """Human-readable mutating native calls recorded by every fake."""
        calls = [f"omp {' '.join(call)}" for call in self.omp_calls()]
        calls.extend(
            f"claude {' '.join(call)}"
            for call in self.claude_calls()
            if _claude_is_mutating(call)
        )
        calls.extend(
            "pi "
            + " ".join(str(arg) for arg in cast(list[object], record.get("argv", [])))
            for record in self.pi_calls()
            if _pi_is_mutating(record)
        )
        return calls

    def staging_digest(self) -> str:
        """Digest staged file names and bytes, including root presence."""
        return tree_digest(self.staging_root)


def _claude_is_mutating(argv: list[str]) -> bool:
    if len(argv) > 2 and argv[1] == "marketplace":
        return argv[2] in _CLAUDE_MARKETPLACE_MUTATIONS
    return len(argv) > 1 and argv[1] in _CLAUDE_MUTATIONS


def _pi_is_mutating(record: dict[str, object]) -> bool:
    argv = record.get("argv")
    return isinstance(argv, list) and bool(argv) and str(argv[0]) in _PI_MUTATIONS


def read_json(path: Path) -> dict[str, object]:
    """Read a JSON object written by a fake manager or host settings file."""
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def tree_digest(root: Path) -> str:
    """Digest a directory tree's names, bytes and presence state."""
    digest = hashlib.sha256()
    digest.update(b"present" if root.exists() else b"absent")
    if root.exists():
        for path in sorted(root.rglob("*")):
            digest.update(str(path.relative_to(root)).encode())
            if path.is_file():
                digest.update(path.read_bytes())
    return digest.hexdigest()


def _make_paths(tmp_path: Path) -> _HostPaths:
    paths = _HostPaths(
        home=tmp_path / "sandbox-home",
        project=tmp_path / "project with spaces",
        bin_dir=tmp_path / "fake-bin",
        agent_dir=tmp_path / "sandbox-home" / ".pi" / "agent",
        state_dir=tmp_path / "fake-state",
        pi_root=tmp_path / "fake-pi",
        xdg_root=tmp_path / "xdg",
    )
    for directory in (
        paths.home,
        paths.project,
        paths.agent_dir,
        paths.state_dir,
        paths.bin_dir,
        paths.pi_root / "bin",
        paths.xdg_root / "config",
        paths.xdg_root / "data",
        paths.xdg_root / "state",
        paths.xdg_root / "cache",
        paths.xdg_root / "runtime",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _host_free_path(current: str) -> str:
    """Drop PATH entries that visibly hold a real host CLI.

    ``os.path.exists`` reports False for any OSError, so an entry that cannot be probed
    (a Windows junction raising ``WinError 448``) is kept rather than aborting setup;
    the fake host directories precede it on PATH, so they still win resolution.
    """
    kept: list[str] = []
    for entry in current.split(os.pathsep):
        if entry and not any(
            os.path.exists(os.path.join(entry, name)) for name in HOST_EXECUTABLES
        ):
            kept.append(entry)
    return os.pathsep.join(kept)


def _activate_environment(monkeypatch: _TestPatch, paths: _HostPaths) -> None:
    variables = {
        "HOME": paths.home,
        "PI_CODING_AGENT_DIR": paths.agent_dir,
        "CLAUDE_CONFIG_DIR": paths.home / ".claude",
        "XDG_CONFIG_HOME": paths.xdg_root / "config",
        "XDG_DATA_HOME": paths.xdg_root / "data",
        "XDG_STATE_HOME": paths.xdg_root / "state",
        "XDG_CACHE_HOME": paths.xdg_root / "cache",
        "XDG_RUNTIME_DIR": paths.xdg_root / "runtime",
        "FAKE_PI_STATE": paths.pi_root / "state.json",
        "FAKE_OMP_STATE": paths.state_dir / "omp.json",
        "FAKE_CLAUDE_STATE": paths.state_dir / "claude.json",
        "FAKE_CLAUDE_LOG": paths.state_dir / "claude-calls.jsonl",
    }
    for name, value in variables.items():
        monkeypatch.setenv(name, str(value))
    for name in _FAILURE_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    path = _host_free_path(os.environ.get("PATH", ""))
    fake_paths = (str(paths.bin_dir), str(paths.pi_root / "bin"), path)
    monkeypatch.setenv("PATH", os.pathsep.join(fake_paths))
    monkeypatch.setattr(Path, "home", lambda: paths.home)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate"
    )
    monkeypatch.setattr(
        slopgate.installer.native.hook_install, "find_binary", lambda: "slopgate"
    )


def install_fake_hosts(monkeypatch: _TestPatch, tmp_path: Path) -> FakeHosts:
    """Install fake managers and isolate host state below ``tmp_path``."""
    isolate_native_data_dirs(monkeypatch, tmp_path)
    paths = _make_paths(tmp_path)
    tests.native.omp_fake.write_fake_omp(paths.bin_dir)
    tests.native.claude_fake.write_fake_claude(paths.bin_dir)
    pi = FakePi(paths.pi_root, paths.agent_dir)
    _activate_environment(monkeypatch, paths)
    return FakeHosts(
        paths.home,
        paths.bin_dir,
        paths.project,
        pi,
        paths.state_dir / "omp.json",
        paths.state_dir / "claude.json",
        paths.state_dir / "claude-calls.jsonl",
    )
