"""Stop/session runtime rules."""

from __future__ import annotations
import re
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import DENY, PERMISSION_REQUEST, PRE_TOOL_USE, METADATA_PATH
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import is_mutating_tool_use, is_safe_read_shell_command

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ._git_quality import is_non_default_branch, is_slopgate_repo, is_worktree

READ_TOOLS = frozenset({"read", "grep", "glob"})
INFRA_FRAGMENTS = (
    "hook-layer/config.json",
    "hook_layer/",
    "slopgate/",
    ".claude/hooks/",
)
CONFIG_FRAGMENTS = ("config/slopgate/config.json", "config/slopgate/rules")


def path_contains_fragment(path_value: str, fragment: str) -> bool:
    """Return True when path matches a protected fragment or a child below it."""
    lowered = path_value.lower()
    normalized_fragment = fragment.rstrip("/")
    return (
        lowered == normalized_fragment
        or lowered.endswith("/" + normalized_fragment)
        or normalized_fragment + "/" in lowered
    )


def is_safe_bash_for_path(ctx: HookContext) -> bool:
    """Return True if the bash command is a safe read-only operation."""
    from slopgate.util.payloads import is_shell_tool

    if not ctx.tool_name or not is_shell_tool(ctx.tool_name):
        return False
    return is_safe_read_shell_command(ctx.shell_command.lower())


def infra_deny(path_value: str, fragment: str, kind: str) -> list[RuleFinding]:
    label = "config" if kind == "config" else "infrastructure"
    return [
        RuleFinding(
            rule_id="GLOBAL-BUILTIN-HOOK-INFRA-EXEC",
            title="Hook layer execution protection",
            severity=Severity.CRITICAL,
            decision=DENY,
            message=f"Modifying the hook layer {label} ({path_value}) is blocked. These files are protected.",
            metadata={METADATA_PATH: path_value, "fragment": fragment, "kind": kind},
        )
    ]


def check_config_path(path_value: str, ctx: HookContext) -> list[RuleFinding] | None:
    """Check config fragments — always protected, no worktree exception."""
    for cfrag in CONFIG_FRAGMENTS:
        if not path_contains_fragment(path_value, cfrag):
            continue
        if is_safe_bash_for_path(ctx):
            return []
        if is_mutating_tool_use(ctx) or not ctx.read_only:
            return infra_deny(path_value, cfrag, "config")
    return None


def check_infra_path(path_value: str, ctx: HookContext) -> list[RuleFinding] | None:
    """Check infra fragments with a narrow slopgate worktree exception."""
    for frag in INFRA_FRAGMENTS:
        if not path_contains_fragment(path_value, frag):
            continue
        if (
            is_worktree(path_value, ctx.cwd)
            and is_slopgate_repo(path_value, ctx.cwd)
            and is_non_default_branch(path_value, ctx.cwd)
        ):
            return []
        if is_safe_bash_for_path(ctx):
            return []
        if is_mutating_tool_use(ctx) or not ctx.read_only:
            return infra_deny(path_value, frag, "infra")
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
        if ctx.tool_name and ctx.tool_name.lower() in READ_TOOLS:
            return []
        for path_value in ctx.candidate_paths:
            cfg = check_config_path(path_value, ctx)
            if cfg is not None:
                return cfg
            infra = check_infra_path(path_value, ctx)
            if infra is not None:
                return infra
        return []


SECURITY_PATTERNS = tuple(
    (
        re.compile(p, re.IGNORECASE)
        for p in (
            "bypass_permissions",
            "allowManagedHooksOnly",
            "disable.*guard",
            "disable.*rule",
            "skip.*validation",
        )
    )
)
SECURITY_EXCLUDED = (
    "hook_layer/",
    "slopgate/",
    "hook-layer/",
    ".claude/hooks/",
    "test_",
    "fixture",
)


def is_security_doc_or_example(path_value: str) -> bool:
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
            if is_security_doc_or_example(lowered):
                continue
            if any((f in lowered for f in SECURITY_EXCLUDED)):
                continue
            for pat in SECURITY_PATTERNS:
                if pat.search(target.content):
                    return [
                        RuleFinding(
                            rule_id=self.rule_id,
                            title=self.title,
                            severity=Severity.HIGH,
                            decision=DENY,
                            message=f"Modifying security guardrail settings is blocked in {target.path}. Do not disable rules or bypass permissions.",
                            metadata={
                                METADATA_PATH: target.path,
                                "pattern": pat.pattern,
                            },
                        )
                    ]
        return []
