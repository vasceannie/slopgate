from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.installer._claude import claude_hooks_block
from slopgate.installer._codex import (
    _install_codex_at,
    codex_hooks_block,
)
from slopgate.installer._shared import InstallAt
from slopgate.installer._pi import _PACKAGE_PAYLOAD, _is_owned_pi_package


def test_claude_session_start_matches_current_sources() -> None:
    hooks = claude_hooks_block("slopgate")

    assert hooks["SessionStart"][0]["matcher"] == (
        "startup|resume|clear|compact|fork"
    )


def test_codex_session_start_matches_current_sources() -> None:
    hooks = codex_hooks_block("slopgate")

    assert hooks["SessionStart"][0]["matcher"] == (
        "startup|resume|clear|compact"
    )


@pytest.mark.parametrize("event", ["PreToolUse", "PermissionRequest", "PostToolUse"])
def test_codex_tool_hooks_cover_supported_local_tools(event: str) -> None:
    hooks = codex_hooks_block("slopgate")

    assert hooks[event][0]["matcher"] == "*"


def test_codex_install_prompts_for_hook_review(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    status = _install_codex_at(
        tmp_path / "hooks.json",
        codex_hooks_block("slopgate"),
        "slopgate",
        InstallAt(root=tmp_path),
    )

    assert status == 0
    assert "Next: /hooks" in capsys.readouterr().out


def test_pi_package_uses_peer_dependency_for_bundled_tui() -> None:
    assert _PACKAGE_PAYLOAD == {
        "private": True,
        "type": "module",
        "dependencies": {"@types/node": "^22.16.5"},
        "peerDependencies": {"@earendil-works/pi-tui": "*"},
    }


@pytest.mark.parametrize("dependency_group", ["dependencies", "peerDependencies"])
def test_pi_package_ownership_accepts_legacy_and_current_metadata(
    dependency_group: str,
) -> None:
    content = json.dumps(
        {dependency_group: {"@earendil-works/pi-tui": "*"}},
    )

    assert _is_owned_pi_package(content)
