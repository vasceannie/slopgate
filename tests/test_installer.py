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


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin
