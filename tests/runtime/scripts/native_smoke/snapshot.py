from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import cast

from .native import package_root, stage_root
from .registration import staged_payload_path
from .sandbox import Sandbox, SmokeFailure


def tree_hash(root: Path) -> str:
    if not root.exists():
        return hashlib.sha256(b"missing").hexdigest()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(os.fsencode(str(path.relative_to(root))))
        if path.is_symlink():
            digest.update(b"L")
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_dir():
            digest.update(b"D")
        elif path.is_file():
            digest.update(b"F")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def staged_version(sandbox: Sandbox, host: str) -> str:
    if host == "pi":
        manifest_path = package_root(sandbox, host) / "package.json"
    else:
        name = "package.json" if host == "omp" else ".claude-plugin/plugin.json"
        manifest_path = staged_payload_path(sandbox, host) / name
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SmokeFailure(
            f"Staged {host} package metadata is malformed: {manifest_path}"
        )
    version = cast(dict[str, object], parsed).get("version")
    if not isinstance(version, str):
        raise SmokeFailure(f"Staged {host} package has no version: {manifest_path}")
    return version


def staged_payload_hash(sandbox: Sandbox, host: str) -> str:
    root = stage_root(sandbox, host)
    if not root.is_dir():
        raise SmokeFailure(f"Staged {host} package root is missing: {root}")
    return tree_hash(root)


def staged_payload_uses_binary(sandbox: Sandbox, host: str, binary: Path) -> bool:
    payload = (
        package_root(sandbox, host)
        if host == "pi"
        else staged_payload_path(sandbox, host)
    )
    expected = str(binary)
    for path in payload.rglob("*"):
        if path.is_file() and path.suffix in {".ts", ".json"}:
            if expected in path.read_text(encoding="utf-8"):
                return True
    return False
