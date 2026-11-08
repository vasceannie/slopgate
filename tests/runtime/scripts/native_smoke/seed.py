from __future__ import annotations

import json
from pathlib import Path

from .native import (
    SCOPES,
    UNRELATED_CLAUDE_ID,
    UNRELATED_OMP_ID,
    UNRELATED_PI_NAME,
    claude_plugins,
    omp_entries,
    pi_package_source,
    run_host,
)
from .sandbox import Sandbox, SmokeFailure


def _write_fixture(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_omp_other(sandbox: Sandbox) -> None:
    root = sandbox.root / "unrelated" / "omp-marketplace"
    package = root / "plugins" / "smoke-unrelated" / "1.0.0"
    manifest: dict[str, object] = {
        "name": "smoke-unrelated",
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "omp": {"extensions": ["./index.ts"]},
        "peerDependencies": {
            "@oh-my-pi/pi-coding-agent": "*",
            "@oh-my-pi/pi-tui": "*",
        },
    }
    catalog: dict[str, object] = {
        "name": "smoke-other",
        "owner": {"name": "Smoke"},
        "plugins": [
            {
                "name": "smoke-unrelated",
                "source": "./plugins/smoke-unrelated/1.0.0",
                "version": "1.0.0",
            }
        ],
    }
    _write_fixture(package / "package.json", json.dumps(manifest, indent=2) + "\n")
    _write_fixture(
        package / "index.ts", "export default function smokeUnrelated() {}\n"
    )
    _write_fixture(
        root / ".omp-plugin" / "marketplace.json", json.dumps(catalog, indent=2) + "\n"
    )
    run_host(sandbox, "omp", ["plugin", "marketplace", "add", str(root)])
    run_host(sandbox, "omp", ["plugin", "install", "--scope", "user", UNRELATED_OMP_ID])


def _seed_claude_other(sandbox: Sandbox) -> None:
    root = sandbox.root / "unrelated" / "claude-marketplace"
    source = root / "plugins" / "smoke-unrelated" / "1.0.0"
    manifest: dict[str, object] = {
        "name": "smoke-unrelated",
        "version": "1.0.0",
        "description": "Smoke plugin",
    }
    catalog: dict[str, object] = {
        "name": "smoke-other",
        "owner": {"name": "Smoke"},
        "plugins": [
            {"name": "smoke-unrelated", "source": "./plugins/smoke-unrelated/1.0.0"}
        ],
    }
    _write_fixture(
        source / ".claude-plugin" / "plugin.json", json.dumps(manifest, indent=2) + "\n"
    )
    _write_fixture(
        root / ".claude-plugin" / "marketplace.json",
        json.dumps(catalog, indent=2) + "\n",
    )
    run_host(sandbox, "claude", ["plugin", "marketplace", "add", str(root)])
    run_host(
        sandbox,
        "claude",
        ["plugin", "install", UNRELATED_CLAUDE_ID, "--scope", "user"],
    )


def _seed_pi_other(sandbox: Sandbox) -> None:
    package = sandbox.root / "unrelated" / "pi-package"
    manifest: dict[str, object] = {
        "name": UNRELATED_PI_NAME,
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "keywords": ["pi-package"],
        "pi": {"extensions": []},
    }
    _write_fixture(package / "package.json", json.dumps(manifest, indent=2) + "\n")
    run_host(sandbox, "pi", ["install", str(package)])
    run_host(sandbox, "pi", ["install", "-l", str(package)])


def seed_unrelated_native_entries(sandbox: Sandbox) -> None:
    _seed_omp_other(sandbox)
    _seed_pi_other(sandbox)
    _seed_claude_other(sandbox)


def assert_unrelated_entries_preserved(sandbox: Sandbox) -> None:
    if not omp_entries(sandbox, UNRELATED_OMP_ID):
        raise SmokeFailure("Unrelated OMP plugin registration was not preserved")
    if not claude_plugins(sandbox, UNRELATED_CLAUDE_ID):
        raise SmokeFailure("Unrelated Claude plugin registration was not preserved")
    package = sandbox.root / "unrelated" / "pi-package"
    for scope in SCOPES:
        entry = pi_package_source(sandbox, scope, package)
        if entry is None:
            raise SmokeFailure(
                f"Unrelated Pi package source was not preserved in {scope} scope"
            )
