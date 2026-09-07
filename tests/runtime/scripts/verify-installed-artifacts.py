"""Prove installed Pi/OMP artifacts load through the pinned native loaders.

Orchestrates the public installer CLI inside disposable roots, then imports and
binds the installed artifacts with each pinned runtime workspace. Every write
lands under a tempdir; the operator's real HOME and agent configuration are
never touched.

Usage: python3 tests/runtime/scripts/verify-installed-artifacts.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OMP_WORKSPACE = REPO_ROOT / "tests" / "runtime" / "omp"
PI_WORKSPACE = REPO_ROOT / "tests" / "runtime" / "pi"
PROJECT_NAME = "project with spaces"
XDG_DIRS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
)


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        detail = "\n".join((completed.stdout.strip(), completed.stderr.strip())).strip()
        raise SystemExit(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return completed.stdout


def child_env(home: Path, agent_dir: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    for key in XDG_DIRS:
        env[key] = str(home / key.lstrip("XDG_").lower())
    if agent_dir is not None:
        env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    else:
        env.pop("PI_CODING_AGENT_DIR", None)
    return env


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hashes(paths: list[Path]) -> dict[Path, str]:
    return {path: sha256(path) for path in paths}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="slopgate-installed-proof-"))
    home = root / "home"
    agent_dir = root / "agent"
    project = root / PROJECT_NAME
    for directory in (home, agent_dir, project):
        directory.mkdir(parents=True)
    (project / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )

    pi_user = home / ".pi" / "agent" / "extensions" / "pi-slopgate"
    pi_project = project / ".pi" / "extensions" / "pi-slopgate"
    omp_user = agent_dir / "extensions" / "omp-slopgate"
    omp_project = project / ".omp" / "extensions" / "omp-slopgate"

    install_pi = [
        "uv",
        "run",
        "slopgate",
        "install",
        "pi",
        "--disable-autoupdate",
        "--install-scope",
        "both",
        "--project-root",
        str(project),
    ]
    install_omp = [
        "uv",
        "run",
        "slopgate",
        "install",
        "omp",
        "--disable-autoupdate",
        "--install-scope",
        "both",
        "--project-root",
        str(project),
    ]

    expected: list[Path] = []
    for site in (pi_user, pi_project, omp_user, omp_project):
        expected.extend((site / "index.ts", site / "package.json"))

    try:
        run(install_pi, cwd=REPO_ROOT, env=child_env(home))
        run(install_omp, cwd=REPO_ROOT, env=child_env(home, agent_dir))
        missing = [path for path in expected if not path.is_file()]
        if missing:
            raise SystemExit(
                f"missing installed artifacts: {[str(path) for path in missing]}"
            )

        discovery = json.loads(
            run(
                ["bun", "run", "scripts/discover-installed.ts", str(project)],
                cwd=OMP_WORKSPACE,
                env=child_env(home, agent_dir),
            )
        )
        if discovery["warnings"]:
            raise SystemExit(f"discovery reported warnings: {discovery['warnings']}")
        if "native" not in discovery["providers"]:
            raise SystemExit(
                f"discovery lacked the native provider: {discovery['providers']}"
            )
        project_items = [
            item
            for item in discovery["items"]
            if item["level"] == "project" and item["name"] == "omp-slopgate"
        ]
        if (
            len(project_items) != 1
            or Path(project_items[0]["path"]).resolve()
            != (omp_project / "index.ts").resolve()
        ):
            raise SystemExit(
                f"unexpected project-level discovery items: {discovery['items']}"
            )

        before = artifact_hashes(expected)
        run(install_pi, cwd=REPO_ROOT, env=child_env(home))
        run(install_omp, cwd=REPO_ROOT, env=child_env(home, agent_dir))
        if artifact_hashes(expected) != before:
            raise SystemExit("reinstall was not byte-stable")

        # Host peer satisfaction for the installed artifacts: resolve peer
        # dependencies against the pinned runtime workspaces.
        node_modules = project / "node_modules"
        node_modules.mkdir()
        (node_modules / "@oh-my-pi").symlink_to(
            OMP_WORKSPACE / "node_modules" / "@oh-my-pi",
            target_is_directory=True,
        )
        (node_modules / "@earendil-works").symlink_to(
            PI_WORKSPACE / "node_modules" / "@earendil-works",
            target_is_directory=True,
        )

        omp_record = root / "omp-payload.json"
        omp_summary = json.loads(
            run(
                [
                    "bun",
                    "run",
                    "scripts/load-installed.ts",
                    str(omp_project / "index.ts"),
                    str(project),
                    str(omp_record),
                ],
                cwd=OMP_WORKSPACE,
                env=child_env(home, agent_dir),
            )
            .strip()
            .splitlines()[-1]
        )
        if not omp_summary.get("loaded") or omp_summary.get("extensions") != 1:
            raise SystemExit(f"OMP installed-artifact load proof failed: {omp_summary}")

        pi_record = root / "pi-payload.json"
        pi_summary = json.loads(
            run(
                [
                    "bun",
                    "run",
                    "scripts/load-installed.ts",
                    str(pi_project / "index.ts"),
                    str(project),
                    str(home / ".pi" / "agent"),
                    str(pi_record),
                ],
                cwd=PI_WORKSPACE,
                env=child_env(home),
            )
            .strip()
            .splitlines()[-1]
        )
        if not pi_summary.get("loaded") or pi_summary.get("extensions", 0) < 1:
            raise SystemExit(f"Pi installed-artifact load proof failed: {pi_summary}")

        pi_paths = [
            path
            for path in expected
            if path.resolve().is_relative_to(pi_user.resolve())
            or path.resolve().is_relative_to(pi_project.resolve())
        ]
        pi_hashes_before = {path: sha256(path) for path in pi_paths}
        run(
            [
                "uv",
                "run",
                "slopgate",
                "uninstall",
                "omp",
                "--disable-autoupdate",
                "--install-scope",
                "both",
                "--project-root",
                str(project),
            ],
            cwd=REPO_ROOT,
            env=child_env(home, agent_dir),
        )
        if omp_user.exists() or omp_project.exists():
            raise SystemExit("OMP uninstall left artifacts behind")
        for path, digest in pi_hashes_before.items():
            if not path.is_file() or sha256(path) != digest:
                raise SystemExit(f"Pi artifact changed during OMP uninstall: {path}")

        run(
            [
                "uv",
                "run",
                "slopgate",
                "uninstall",
                "pi",
                "--disable-autoupdate",
                "--install-scope",
                "both",
                "--project-root",
                str(project),
            ],
            cwd=REPO_ROOT,
            env=child_env(home),
        )
        pi_leftovers = [
            path
            for path in (*pi_user.rglob("*"), *pi_project.rglob("*"))
            if path.is_file() and ".slopgate-bak-" not in path.name
        ]
        if pi_leftovers:
            raise SystemExit(
                f"Pi uninstall left owned artifacts behind: {[str(p) for p in pi_leftovers]}"
            )

        print(
            json.dumps(
                {
                    "byte_stable_reinstall": True,
                    "cross_harness_preservation": True,
                    "omp_loaded": omp_summary,
                    "pi_loaded": pi_summary,
                    "project": str(project),
                    "result": "pass",
                }
            )
        )
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
