"""Sandbox setup and artifact assertions for Pi native installer tests."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Protocol, cast

import slopgate.installer
import slopgate.installer.native.entry
import slopgate.installer._shared
from slopgate.installer.native.packages import native_host_root
from slopgate.installer.native.pi.settings import settings_path
from tests.native.environment import isolate_native_data_dirs
from tests.native.pi_fake import FakePi

_TEST_BINARY = "/tmp/slopgate-test-bin"


class _TestPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...

    def setenv(self, name: str, value: str) -> None: ...


class _CaptureResult(Protocol):
    @property
    def out(self) -> str: ...


class _Capture(Protocol):
    def readouterr(self) -> _CaptureResult: ...


@dataclass(slots=True)
class PiHarness:
    home: Path
    agent_dir: Path
    project: Path
    package_root: Path
    user_settings: Path
    project_settings: Path
    fake: FakePi
    install: Callable[..., int]
    uninstall: Callable[..., int]


def make_harness(tmp_path: Path, monkeypatch: _TestPatch) -> PiHarness:
    """Build an isolated project, Pi agent directory and fake native manager."""
    isolate_native_data_dirs(monkeypatch, tmp_path)
    home = tmp_path / "sandbox-home"
    agent_dir = home / "pi-agent-isolated"
    project = tmp_path / "project with spaces"
    home.mkdir()
    agent_dir.mkdir()
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(
        slopgate.installer._shared,
        "find_binary",
        lambda: _TEST_BINARY,
    )
    monkeypatch.setattr(
        slopgate.installer.native.entry,
        "find_binary",
        lambda: _TEST_BINARY,
    )
    fake = FakePi(tmp_path / "fake-pi", agent_dir)
    fake.activate(monkeypatch)
    return PiHarness(
        home,
        agent_dir,
        project,
        native_host_root("pi") / "package",
        settings_path("user", project),
        settings_path("project", project),
        fake,
        partial(
            slopgate.installer.install_platform,
            "pi",
            install_scope="both",
            project_root=project,
        ),
        partial(
            slopgate.installer.uninstall_platform,
            "pi",
            install_scope="both",
            project_root=project,
        ),
    )


def write_user_settings_text(harness: PiHarness, text: str) -> None:
    """Write user settings content, creating its parent directory as needed."""
    harness.user_settings.parent.mkdir(parents=True, exist_ok=True)
    harness.user_settings.write_text(text, encoding="utf-8")


def legacy_paths(harness: PiHarness, scope: str) -> tuple[Path, ...]:
    extensions = (
        harness.agent_dir / "extensions"
        if scope == "user"
        else (harness.project / ".pi" / "extensions")
    )
    package = extensions / "pi-slopgate"
    return (
        package / "index.ts",
        package / "index.js",
        package / "package.json",
        package / "config.json",
        extensions / "slopgate.ts",
    )


def legacy_active(harness: PiHarness, scope: str) -> bool:
    """Return whether any legacy entry point for *scope* still exists."""
    return any(path.exists() for path in legacy_paths(harness, scope))


def seed_legacy(
    harness: PiHarness, scope: str, *, keep_sibling: bool = True
) -> dict[Path, tuple[bytes, int]]:
    paths = legacy_paths(harness, scope)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    marker = "/* Pi Slopgate Extension */\nconst SLOPGATE_ARGV = [];\n"
    handler = "// slopgate handle --platform pi\n"
    paths[0].write_text(marker + handler, encoding="utf-8")
    paths[1].write_text("// pi-slopgate\n" + handler, encoding="utf-8")
    paths[2].write_text(
        json.dumps({"peerDependencies": {"@earendil-works/pi-tui": "*"}}),
        encoding="utf-8",
    )
    paths[3].write_text(json.dumps({"name": "pi-slopgate"}), encoding="utf-8")
    paths[4].write_text(marker + handler, encoding="utf-8")
    if keep_sibling:
        (paths[0].parent / "keep.txt").write_text(
            "unrelated sibling\n", encoding="utf-8"
        )
    return {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in paths
    }


def seed_both_scopes(
    harness: PiHarness,
) -> tuple[dict[Path, tuple[bytes, int]], dict[Path, tuple[bytes, int]]]:
    """Seed recognized legacy files in the user and project Pi scopes."""
    return seed_legacy(harness, "user"), seed_legacy(harness, "project")


def seed_unrecognized_legacy_directory(
    harness: PiHarness, files: tuple[tuple[str, str], ...]
) -> Path:
    """Place foreign or incomplete metadata in the old package directory."""
    package = legacy_paths(harness, "user")[0].parent
    package.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (package / name).write_text(content, encoding="utf-8")
    return package


def package_sources(settings: Path) -> list[Path]:
    if not settings.exists():
        return []
    document = cast(dict[str, object], json.loads(settings.read_text(encoding="utf-8")))
    raw_entries = document.get("packages", [])
    if not isinstance(raw_entries, list):
        return []
    result: list[Path] = []
    for entry in cast(list[object], raw_entries):
        if isinstance(entry, str):
            source_text = entry
        elif isinstance(entry, dict):
            entry_object = cast(dict[str, object], entry)
            candidate = entry_object.get("source")
            if not isinstance(candidate, str):
                continue
            source_text = candidate
        else:
            continue
        source = Path(source_text).expanduser()
        result.append(
            (source if source.is_absolute() else settings.parent / source).resolve()
        )
    return result


def registered_sources(harness: PiHarness) -> tuple[list[Path], list[Path]]:
    """Return package sources registered for user and project scope."""
    return (
        package_sources(harness.user_settings),
        package_sources(harness.project_settings),
    )


def backup_bytes_match(seeded: dict[Path, tuple[bytes, int]]) -> bool:
    for path, (content, mode) in seeded.items():
        backups = list(path.parent.glob(path.name + ".slopgate-bak-*"))
        if not backups:
            return False
        if backups[0].read_bytes() != content:
            return False
        if stat.S_IMODE(backups[0].stat().st_mode) != mode:
            return False
    return True


def backups_preserved(*seeds: dict[Path, tuple[bytes, int]]) -> bool:
    """Return whether every seeded legacy artifact has a byte- and mode-matching backup."""
    return all(backup_bytes_match(seed) for seed in seeds)


def original_artifacts_match(seeded: dict[Path, tuple[bytes, int]]) -> bool:
    for path, (content, mode) in seeded.items():
        if not path.exists() or path.read_bytes() != content:
            return False
        if stat.S_IMODE(path.stat().st_mode) != mode:
            return False
    return True


def artifacts_unchanged(*seeds: dict[Path, tuple[bytes, int]]) -> bool:
    """Return whether every seeded legacy artifact remains byte- and mode-identical."""
    return all(original_artifacts_match(seed) for seed in seeds)


def tree_digest(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(path.relative_to(root)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def untouched_by_install(harness: PiHarness) -> bool:
    """Return whether install created no staged package or native Pi calls."""
    return not harness.package_root.exists() and harness.fake.calls() == []


def native_actions(fake: FakePi) -> list[str]:
    actions: list[str] = []
    for record in fake.calls():
        argv = record.get("argv")
        if isinstance(argv, list) and argv and isinstance(argv[0], str):
            actions.append(argv[0])
    return actions


def native_mutations(fake: FakePi) -> list[str]:
    return [
        action
        for action in native_actions(fake)
        if action in {"install", "remove", "uninstall"}
    ]


def native_cwds(fake: FakePi) -> list[str]:
    return [
        cwd for record in fake.calls() if isinstance((cwd := record.get("cwd")), str)
    ]


def run_and_capture(
    capsys: _Capture, action: Callable[..., int], **options: object
) -> tuple[int, str]:
    """Run a harness action and return its status plus captured output."""
    status = action(**options)
    return status, capsys.readouterr().out


def no_approval_flags(fake: FakePi) -> bool:
    for record in fake.calls():
        argv = record.get("argv")
        if not isinstance(argv, list):
            continue
        for argument in cast(list[object], argv):
            if isinstance(argument, str) and argument in {
                "--approve",
                "--no-approve",
            }:
                return False
    return True
