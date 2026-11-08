"""Versioned renderer for Slopgate's stable native Pi package."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import partial

from slopgate.installer.native.model import VERSION_KEY
from slopgate.installer.native.packages import (
    PackagePlan,
    PayloadRenderer,
    package_plan,
)
from slopgate.installer.native.pi.legacy import render_pi_extension

__all__ = ["PI_PACKAGE_NAME", "build_pi_plan", "pi_manifest", "pi_payload"]

PI_PACKAGE_NAME = "pi-slopgate"
_PI_PEER_DEPENDENCIES = {
    "@earendil-works/pi-coding-agent": "*",
    "@earendil-works/pi-tui": "*",
}


def pi_manifest(version: str) -> dict[str, object]:
    """Return the native Pi package manifest for one staged version."""
    return {
        "name": PI_PACKAGE_NAME,
        VERSION_KEY: version,
        "private": True,
        "type": "module",
        "keywords": ["pi-package"],
        "pi": {"extensions": ["./index.ts"]},
        "peerDependencies": dict(_PI_PEER_DEPENDENCIES),
    }


def pi_payload(template: str, binary: str) -> Callable[[str], dict[str, str]]:
    """Bind the existing extension template to a staged manifest version."""
    return partial(_render_pi_payload, template, binary)


def _render_pi_payload(template: str, binary: str, version: str) -> dict[str, str]:
    manifest = json.dumps(pi_manifest(version), indent=2) + "\n"
    return {
        "package.json": manifest,
        "index.ts": render_pi_extension(template, binary),
    }


def build_pi_plan(template: str, binary: str) -> PackagePlan:
    """Plan the single stable-path Pi package without filesystem writes."""
    render: PayloadRenderer = pi_payload(template, binary)
    return package_plan("pi", render=render)
