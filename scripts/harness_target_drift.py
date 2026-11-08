"""Report harness releases that are ahead of the version Slopgate declares it targets.

Harnesses release too often to pin in tests, so nothing here gates or bumps
anything. A few harnesses are different: OpenCode's version is a compatibility
claim in production code (``_OPENCODE_API_TARGET``), and the real-host contract
suite skips itself on any other version. This reports when a newer release
exists so adopting it is a deliberate change instead of a silent skip.

The release source is the harness's npm package (for OpenCode 2.x that is the
lockstep plugin SDK, ``@opencode/plugin``; ``opencode-ai`` is the 1.x line).

Usage:
    uv run python scripts/harness_target_drift.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPENCODE_IDENTITY_PATH = REPOSITORY_ROOT / "src/slopgate/installer/opencode_identity.py"
OPENCODE_TARGET_PATTERN = re.compile(r'^_OPENCODE_API_TARGET = "([^"]+)"', re.MULTILINE)
VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)+")
REGISTRY_BASE_URL = "https://registry.npmjs.org/"
RELEASE_CHANNEL = "latest"
REGISTRY_TIMEOUT_SECONDS = 30

EXIT_OK = 0
EXIT_FAILED = 1


class DriftCheckError(RuntimeError):
    """Raised when release metadata or Slopgate's declared target cannot be read."""


def extract_version(value: str) -> str:
    match = VERSION_PATTERN.search(value)
    if match is None:
        raise DriftCheckError(f"No version number in {value!r}")
    return match.group(0)


def opencode_api_target(path: Path = OPENCODE_IDENTITY_PATH) -> str:
    """Read the OpenCode version Slopgate targets, without importing private names."""
    match = OPENCODE_TARGET_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise DriftCheckError(f"{path} has no _OPENCODE_API_TARGET constant")
    return match.group(1)


@dataclass(frozen=True)
class DeclaredTarget:
    """A harness whose version Slopgate declares in code, and where it is released."""

    name: str
    package: str
    read_target: Callable[[], str]


DECLARED_TARGETS: tuple[DeclaredTarget, ...] = (
    DeclaredTarget("opencode", "@opencode/plugin", opencode_api_target),
)


@dataclass(frozen=True)
class Drift:
    name: str
    target: str
    released: str
    installed: str | None

    @property
    def ahead(self) -> bool:
        newer, older = (
            [int(part) for part in extract_version(version).split(".")]
            for version in (self.released, self.target)
        )
        return newer > older


def released_version(metadata: object) -> str:
    tags = (
        cast(dict[str, object], metadata).get("dist-tags")
        if isinstance(metadata, dict)
        else None
    )
    version = (
        cast(dict[str, object], tags).get(RELEASE_CHANNEL)
        if isinstance(tags, dict)
        else None
    )
    if not isinstance(version, str):
        raise DriftCheckError(f"npm metadata has no {RELEASE_CHANNEL!r} dist-tag")
    return extract_version(version)


def fetch_registry_metadata(package: str) -> object:
    request = urllib.request.Request(
        REGISTRY_BASE_URL + package,
        headers={"Accept": "application/vnd.npm.install-v1+json"},
    )
    with urllib.request.urlopen(request, timeout=REGISTRY_TIMEOUT_SECONDS) as response:
        return json.load(response)


def installed_version(name: str) -> str | None:
    try:
        result = subprocess.run(
            [name, "--version"], check=False, capture_output=True, text=True
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return extract_version(result.stdout + result.stderr)


def find_drift(targets: Sequence[DeclaredTarget]) -> list[Drift]:
    return [
        Drift(
            name=declared.name,
            target=declared.read_target(),
            released=released_version(fetch_registry_metadata(declared.package)),
            installed=installed_version(declared.name),
        )
        for declared in targets
    ]


def main() -> int:
    try:
        drifts = find_drift(DECLARED_TARGETS)
    except (DriftCheckError, OSError) as error:
        print(f"Could not check harness release drift: {error}", file=sys.stderr)
        return EXIT_FAILED
    ahead = [drift for drift in drifts if drift.ahead]
    for drift in ahead:
        print(
            f"{drift.name} {drift.released} released; Slopgate targets {drift.target}; "
            f"installed {drift.installed or 'none'}"
        )
    if not ahead:
        print("No harness release is ahead of Slopgate's declared targets")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
