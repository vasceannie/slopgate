from __future__ import annotations

from vibeforcer.installer import _codex_hooks_block


def test_codex_hooks_cover_non_bash_mutating_tools() -> None:
    hooks = _codex_hooks_block("vibeforcer")
    pre = hooks["PreToolUse"][0]
    post = hooks["PostToolUse"][0]
    permission = hooks["PermissionRequest"][0]
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    permission_matcher = str(permission.get("matcher", ""))
    for tool_name in ("Write", "Edit", "MultiEdit", "Patch", "Delete", "Create"):
        assert tool_name in pre_matcher
        assert tool_name in post_matcher
        assert tool_name in permission_matcher
