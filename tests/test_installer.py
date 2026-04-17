from __future__ import annotations

import vibeforcer.installer as installer_module
from typing import Any


def _hook_builder(name: str) -> Any:
    return getattr(installer_module, name)


def test_codex_hooks_are_bash_only() -> None:
    hooks = _hook_builder("_codex_hooks_block")("vibeforcer")
    pre = hooks["PreToolUse"][0]
    post = hooks["PostToolUse"][0]
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    assert pre_matcher == "Bash"
    assert post_matcher == "Bash"
    assert "PermissionRequest" not in hooks


def test_claude_hooks_include_cwd_changed() -> None:
    hooks = _hook_builder("_claude_hooks_block")("vibeforcer")
    assert "CwdChanged" in hooks
