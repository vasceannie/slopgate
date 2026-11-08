"""Behavioral tests for isolated native smoke environments."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.native.launchers import write_python_launcher
from tests.runtime.scripts.native_smoke import sandbox
from tests.runtime.scripts.native_smoke.sandbox import Sandbox


@pytest.mark.skipif(
    os.name == "nt", reason="This check requires POSIX symlink execution"
)
def test_claude_basename_resolves_symlinked_host_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_sandbox, fake_claude_dir = _make_fake_sandbox(tmp_path, monkeypatch)
    environment = isolated_sandbox.environment("claude")
    completed = subprocess.run(
        ["claude"],
        cwd=isolated_sandbox.root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, "Claude basename execution should succeed"
    assert completed.stdout.strip() == "intended Claude target", (
        "Claude basename execution should reach the symlink target"
    )
    assert str(fake_claude_dir) in environment["PATH"].split(os.pathsep), (
        "Sandbox PATH should retain the lexical symlink directory"
    )


def _make_fake_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Sandbox, Path]:
    root = tmp_path / "smoke-test"
    root.mkdir()
    host_names = ("omp", "pi", "claude", "bun", "node", "git")
    host_directories = {name: root / f"{name}-bin" for name in host_names}
    for directory in host_directories.values():
        directory.mkdir()
    target = write_python_launcher(
        root / "claude-target", "claude-target", 'print("intended Claude target")\n'
    )
    (host_directories["claude"] / "claude").symlink_to(target)
    for name in ("omp", "pi", "bun", "node", "git"):
        write_python_launcher(host_directories[name], name, "raise SystemExit(0)\n")
    repo = root / "checkout"
    slopgate_binary = write_python_launcher(
        repo / ".venv" / "bin", "slopgate", "raise SystemExit(0)\n"
    )
    path_entries = [str(directory) for directory in host_directories.values()]
    path_entries.append(str(slopgate_binary.parent))
    monkeypatch.setenv("PATH", os.pathsep.join(path_entries))
    profile_root = root / "profile"

    def fixed_temp_directory(prefix: str | None = None) -> str:
        _ = prefix
        return str(profile_root)

    monkeypatch.setattr(sandbox.tempfile, "mkdtemp", fixed_temp_directory)
    monkeypatch.setattr(sandbox, "_SYSTEM_PATHS", ())
    return sandbox.create_sandbox(repo), host_directories["claude"]
