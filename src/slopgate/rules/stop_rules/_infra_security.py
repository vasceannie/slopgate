"""Stop/session runtime rules."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from typing_extensions import override
from vibeforcer.constants import (
    DENY,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
    METADATA_PATH,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.rules.common import is_safe_read_shell_command
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._git_quality import _is_non_default_branch as _is_non_default_branch, _is_vibeforcer_repo as _is_vibeforcer_repo, _is_worktree as _is_worktree


_READ_TOOLS = frozenset({"read", "grep", "glob"})

_INFRA_FRAGMENTS = (
    "hook-layer/config.json",
    "hook_layer/",
    "vibeforcer/",
    ".claude/hooks/",
)

_CONFIG_FRAGMENTS = (
    "config/vibeforcer/config.json",
    "config/vibeforcer/rules",
)


def _path_contains_fragment(path_value: str, fragment: str) -> bool:
    """Return True when path matches a protected fragment or a child below it."""
    lowered = path_value.lower()
    normalized_fragment = fragment.rstrip("/")
    return (
        lowered == normalized_fragment
        or lowered.endswith("/" + normalized_fragment)
        or normalized_fragment + "/" in lowered
    )


def _is_safe_bash_for_path(ctx: HookContext) -> bool:
    """Return True if the bash command is a safe read-only operation."""
    from vibeforcer.util.payloads import is_shell_tool

    if not ctx.tool_name or not is_shell_tool(ctx.tool_name):
        return False
    return is_safe_read_shell_command(ctx.shell_command.lower())


def _is_modifying_tool(ctx: HookContext) -> bool:
    """Return True if the tool can modify files (bash or edit-like)."""
    from vibeforcer.util.payloads import is_shell_tool

    if ctx.tool_name and is_shell_tool(ctx.tool_name):
        return True
    from vibeforcer.util.payloads import is_edit_like_tool

    return is_edit_like_tool(ctx.tool_name)


def _infra_deny(path_value: str, fragment: str, kind: str) -> list[RuleFinding]:
    label = "config" if kind == "config" else "infrastructure"
    return [
        RuleFinding(
            rule_id="GLOBAL-BUILTIN-HOOK-INFRA-EXEC",
            title="Hook layer execution protection",
            severity=Severity.CRITICAL,
            decision=DENY,
            message=(
                f"Modifying the hook layer {label} "
                f"({path_value}) is blocked. "
                f"These files are protected."
            ),
            metadata={METADATA_PATH: path_value, "fragment": fragment, "kind": kind},
        )
    ]


def _check_config_path(path_value: str, ctx: HookContext) -> list[RuleFinding] | None:
    """Check config fragments — always protected, no worktree exception."""
    for cfrag in _CONFIG_FRAGMENTS:
        if not _path_contains_fragment(path_value, cfrag):
            continue
        if _is_safe_bash_for_path(ctx):
            return []
        if _is_modifying_tool(ctx):
            return _infra_deny(path_value, cfrag, "config")
    return None


def _check_infra_path(path_value: str, ctx: HookContext) -> list[RuleFinding] | None:
    """Check infra fragments with a narrow vibeforcer worktree exception."""
    for frag in _INFRA_FRAGMENTS:
        if not _path_contains_fragment(path_value, frag):
            continue
        if (
            _is_worktree(path_value, ctx.cwd)
            and _is_vibeforcer_repo(path_value, ctx.cwd)
            and _is_non_default_branch(path_value, ctx.cwd)
        ):
            return []
        if _is_safe_bash_for_path(ctx):
            return []
        if _is_modifying_tool(ctx):
            return _infra_deny(path_value, frag, "infra")
    return None


class HookInfraExecProtectionRule(Rule):
    """Block modification of hook layer infrastructure and config."""

    rule_id: str = "GLOBAL-BUILTIN-HOOK-INFRA-EXEC"
    title: str = "Hook layer execution protection"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if ctx.tool_name and ctx.tool_name.lower() in _READ_TOOLS:
            return []
        for path_value in ctx.candidate_paths:
            cfg = _check_config_path(path_value, ctx)
            if cfg is not None:
                return cfg
            infra = _check_infra_path(path_value, ctx)
            if infra is not None:
                return infra
        return []


# ---------------------------------------------------------------------------
# Rulebook security
# ---------------------------------------------------------------------------

_SECURITY_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        "bypass_permissions",
        "allowManagedHooksOnly",
        r"disable.*guard",
        r"disable.*rule",
        r"skip.*validation",
    )
)

_SECURITY_EXCLUDED = (
    "hook_layer/",
    "vibeforcer/",
    "hook-layer/",
    ".claude/hooks/",
    "test_",
    "fixture",
)


def _is_security_doc_or_example(path_value: str) -> bool:
    lowered = path_value.lower().replace("\\", "/")
    if lowered.startswith("docs/") and lowered.endswith(".md"):
        return True
    if lowered.startswith("docs/examples/") and lowered.endswith(".json"):
        return True
    return False


class RulebookSecurityRule(Rule):
    """Prevent disabling or weakening security guardrails."""

    rule_id: str = "BUILTIN-RULEBOOK-SECURITY"
    title: str = "Rulebook security guardrails"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        for target in ctx.content_targets:
            lowered = target.path.lower()
            if _is_security_doc_or_example(lowered):
                continue
            if any(f in lowered for f in _SECURITY_EXCLUDED):
                continue
            for pat in _SECURITY_PATTERNS:
                if pat.search(target.content):
                    return [
                        RuleFinding(
                            rule_id=self.rule_id,
                            title=self.title,
                            severity=Severity.HIGH,
                            decision=DENY,
                            message=(
                                "Modifying security guardrail "
                                f"settings is blocked in {target.path}. "
                                "Do not disable rules or "
                                "bypass permissions."
                            ),
                            metadata={
                                METADATA_PATH: target.path,
                                "pattern": pat.pattern,
                            },
                        )
                    ]
        return []
