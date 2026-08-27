#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run verify-real-system.py
# 3. Or make executable and run:
#      chmod +x verify-real-system.py && ./verify-real-system.py
# ──────────────────

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WORKSPACE_ROOT: Final = Path(__file__).resolve().parent.parent
REPO_ROOT: Final = WORKSPACE_ROOT.parents[2]
TEMPLATE_PATH: Final = REPO_ROOT / "src/slopgate/resources/omp_extension.ts"
PLACEHOLDER: Final = '["__SLOPGATE_BIN__"]'
MANIFEST_BYTES: Final = b'''{
  "name": "omp-slopgate",
  "private": true,
  "type": "module",
  "omp": {
    "extensions": [
      "./index.ts"
    ]
  },
  "peerDependencies": {
    "@oh-my-pi/pi-coding-agent": "*",
    "@oh-my-pi/pi-tui": "*"
  }
}
'''
OWNERSHIP_MARKERS: Final = (
    "OMP Slopgate Extension",
    "const SLOPGATE_ARGV",
    "slopgate handle --platform omp",
)
ROUTING_ENV_KEYS: Final = (
    "SLOPGATE_CONFIG",
    "SLOPGATE_CONFIG_DIR",
    "SLOPGATE_ROOT",
    "CLAUDE_HOOK_LAYER_ROOT",
    "HOOK_LAYER_ROOT",
    "OMP_AGENT_DIR",
)


class SystemVerificationError(RuntimeError):
    """Report one failed real-system contract assertion."""

    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"OMP real-system verification failed: {detail}")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured subprocess outcome."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Isolated subprocess working directory and environment."""

    cwd: Path
    environment: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class LifecyclePaths:
    """Contained user and project OMP artifacts for one lifecycle run."""

    root: Path
    project: Path
    user_agent: Path

    @property
    def user_index(self) -> Path:
        return self.user_agent / "extensions/omp-slopgate/index.ts"

    @property
    def project_index(self) -> Path:
        return self.project / ".omp/extensions/omp-slopgate/index.ts"

    @property
    def artifacts(self) -> tuple[Path, Path, Path, Path]:
        return (
            self.user_index,
            self.user_index.with_name("package.json"),
            self.project_index,
            self.project_index.with_name("package.json"),
        )


def run_captured(command: Sequence[str], context: CommandContext) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=context.cwd,
        env=context.environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def require_success(command: Sequence[str], result: CommandResult) -> None:
    if result.returncode != 0:
        rendered = " ".join(command)
        raise SystemVerificationError(
            f"command failed ({result.returncode}): {rendered}\nstdout={result.stdout}\nstderr={result.stderr}"
        )


def run_streamed(command: Sequence[str], context: CommandContext) -> None:
    completed = subprocess.run(command, cwd=context.cwd, env=context.environment, check=False)
    if completed.returncode != 0:
        raise SystemVerificationError(f"command failed ({completed.returncode}): {' '.join(command)}")


def assert_contained(paths: LifecyclePaths, environment: Mapping[str, str]) -> None:
    root = paths.root.resolve()
    candidates = [*paths.artifacts]
    candidates.extend(Path(environment[key]) for key in environment if key.startswith("XDG_") or key == "HOME")
    for candidate in candidates:
        if not candidate.resolve().is_relative_to(root):
            raise SystemVerificationError(f"path escaped isolated root: {candidate}")


def assert_installed(index_path: Path, expected_index: bytes) -> None:
    manifest_path = index_path.with_name("package.json")
    if index_path.read_bytes() != expected_index:
        raise SystemVerificationError(f"unexpected extension bytes: {index_path}")
    if manifest_path.read_bytes() != MANIFEST_BYTES:
        raise SystemVerificationError(f"unexpected manifest bytes: {manifest_path}")
    index_text = expected_index.decode()
    if not all(marker in index_text for marker in OWNERSHIP_MARKERS):
        raise SystemVerificationError(f"ownership markers missing: {index_path}")


def assert_artifacts_absent(paths: LifecyclePaths) -> None:
    remaining = [str(path) for path in paths.artifacts if path.exists()]
    if remaining:
        raise SystemVerificationError(f"uninstall left artifacts: {', '.join(remaining)}")


def isolated_environment(paths: LifecyclePaths) -> dict[str, str]:
    environment = dict(os.environ)
    for key in ROUTING_ENV_KEYS:
        environment.pop(key, None)
    environment.update(
        {
            "CI": "1",
            "HOME": str(paths.root / "home"),
            "NO_COLOR": "1",
            "PI_CODING_AGENT_DIR": str(paths.user_agent),
            "XDG_CACHE_HOME": str(paths.root / "xdg-cache"),
            "XDG_CONFIG_HOME": str(paths.root / "xdg-config"),
            "XDG_DATA_HOME": str(paths.root / "xdg-data"),
            "XDG_RUNTIME_DIR": str(paths.root / "xdg-runtime"),
            "XDG_STATE_HOME": str(paths.root / "xdg-state"),
        }
    )
    return environment


def expected_index_bytes(context: CommandContext) -> bytes:
    binary = shutil.which("slopgate", path=context.environment.get("PATH"))
    invocation = [sys.executable, "-m", "slopgate"] if binary is None else [binary]
    source = TEMPLATE_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in source:
        raise SystemVerificationError("production template placeholder is missing")
    return source.replace(PLACEHOLDER, json.dumps(invocation)).encode()


def lifecycle_command(action: str, paths: LifecyclePaths, *, dry_run: bool = False) -> list[str]:
    command = [
        "uv",
        "run",
        "--project",
        str(REPO_ROOT),
        "slopgate",
        action,
        "omp",
        "--disable-autoupdate",
        "--install-scope",
        "both",
        "--project-root",
        str(paths.project),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def verify_lifecycle(paths: LifecyclePaths, context: CommandContext) -> None:
    expected_index = expected_index_bytes(context)
    assert_contained(paths, context.environment)
    dry_run_command = lifecycle_command("install", paths, dry_run=True)
    dry_run = run_captured(dry_run_command, context)
    require_success(dry_run_command, dry_run)
    if any(path.exists() for path in paths.artifacts):
        raise SystemVerificationError("dry-run created OMP artifacts")
    for artifact in paths.artifacts:
        if str(artifact) not in dry_run.stdout:
            raise SystemVerificationError(f"dry-run omitted artifact: {artifact}")

    assert_contained(paths, context.environment)
    install_command = lifecycle_command("install", paths)
    require_success(install_command, run_captured(install_command, context))
    assert_installed(paths.user_index, expected_index)
    assert_installed(paths.project_index, expected_index)

    assert_contained(paths, context.environment)
    discovery_command = ["bun", "run", "scripts/discover-installed.ts", str(paths.project)]
    discovery = run_captured(discovery_command, CommandContext(WORKSPACE_ROOT, context.environment))
    require_success(discovery_command, discovery)
    expected_discovery = json.dumps(
        {
            "items": [
                {"level": "project", "name": "omp-slopgate", "path": str(paths.project_index)}
            ],
            "providers": ["native"],
            "warnings": [],
        },
        separators=(",", ":"),
    )
    if discovery.stdout != expected_discovery:
        raise SystemVerificationError(f"unexpected discovery output: {discovery.stdout}")

    paths.user_index.write_text("// unowned extension\n", encoding="utf-8")
    assert_contained(paths, context.environment)
    uninstall_command = lifecycle_command("uninstall", paths)
    refusal = run_captured(uninstall_command, context)
    if refusal.returncode == 0 or "Refusing to remove unrecognized OMP extension" not in refusal.stdout:
        raise SystemVerificationError("doctored user extension was not refused")
    if not paths.user_index.exists() or not paths.project_index.exists():
        raise SystemVerificationError("refusal removed a protected or unvisited extension")

    paths.user_index.write_bytes(expected_index)
    paths.user_index.with_name("package.json").write_bytes(MANIFEST_BYTES)
    assert_contained(paths, context.environment)
    require_success(uninstall_command, run_captured(uninstall_command, context))
    assert_artifacts_absent(paths)


def verify_harness(context: CommandContext) -> None:
    for command in (
        ["bun", "install", "--frozen-lockfile"],
        ["bun", "run", "test"],
        ["bun", "run", "typecheck"],
        ["bun", "run", "verify:snapshot", "--require", "all"],
        ["bun", "run", "verify:package"],
    ):
        run_streamed(command, CommandContext(WORKSPACE_ROOT, context.environment))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="slopgate-omp-system-") as temporary_root:
        root = Path(temporary_root).resolve()
        paths = LifecyclePaths(root, root / "project", root / "omp-agent")
        paths.project.mkdir(parents=True)
        environment = isolated_environment(paths)
        for key in ("HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "XDG_STATE_HOME"):
            Path(environment[key]).mkdir(parents=True)
        Path(environment["XDG_RUNTIME_DIR"]).chmod(0o700)
        context = CommandContext(paths.project, environment)
        verify_lifecycle(paths, context)
        verify_harness(context)


if __name__ == "__main__":
    main()
