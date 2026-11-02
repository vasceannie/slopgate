"""Contract checks against a real OpenCode 2.2.5 server, not a fake context."""

from __future__ import annotations

import pytest

from slopgate.installer.opencode_identity import opencode_runtime_version
from slopgate.opencode_tool_capabilities import (
    EFFECTFUL_TOOL_IDS,
    READ_ONLY_TOOL_IDS,
)
from tests.integration.real_host_support import HostObservation

_PINNED_RUNTIME = "2.2.5"

pytestmark = pytest.mark.skipif(
    _PINNED_RUNTIME not in opencode_runtime_version(),
    reason=f"OpenCode {_PINNED_RUNTIME} is required",
)


def test_host_activates_generated_plugins(real_opencode_host: HostObservation) -> None:
    assert real_opencode_host.plugins["slopgate"] == "active", (
        "the rendered enforcement plugin must load on the real host"
    )
    assert real_opencode_host.plugins["slopgate.isx"] == "active", (
        "the rendered isx plugin must load on the real host"
    )


def test_repair_verifier_is_not_hidden_behind_code_mode(
    real_opencode_host: HostObservation,
) -> None:
    assert real_opencode_host.tool_codemode["slopgate_verify_repair"] is False, (
        "with Code Mode on, only codemode=false tools are directly callable"
    )


def test_native_mutation_tools_are_direct(real_opencode_host: HostObservation) -> None:
    direct = {
        tool
        for tool, codemode in real_opencode_host.tool_codemode.items()
        if codemode is False
    }

    assert {"write", "edit", "patch", "shell", "read"} <= direct, (
        "the repair flow depends on these native tools staying directly callable"
    )


def test_every_host_tool_is_declared(real_opencode_host: HostObservation) -> None:
    undeclared = {
        tool
        for tool in real_opencode_host.tool_codemode
        if not tool.startswith("isx_")
        and tool not in READ_ONLY_TOOL_IDS | EFFECTFUL_TOOL_IDS
    }

    assert undeclared == set(), "new host tools must be classified in the registry"


def test_subdirectory_session_location_differs_from_project(
    real_opencode_host: HostObservation,
) -> None:
    assert real_opencode_host.session_directory.name == "sub", (
        "sessions report the opened directory, which relative paths resolve against"
    )
    assert real_opencode_host.project_directory == (
        real_opencode_host.session_directory.parent
    ), "the plugin location must expose the project root used as the repair worktree"


def test_runtime_version_matches_the_pinned_sdk(
    real_opencode_host: HostObservation,
) -> None:
    assert real_opencode_host.version == _PINNED_RUNTIME, (
        "these contract checks are only meaningful against the pinned host"
    )
