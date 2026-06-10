"""Stop/session runtime rules."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate._types import bool_value, object_dict, string_value
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

if TYPE_CHECKING:
    from slopgate.context import HookContext


GIT_COMMANDS: list[tuple[list[str], str]] = [
    (["git", "log", "--oneline", "-10"], "## Recent commits\n```\n{output}\n```"),
    (["git", "status", "--short"], "## Working tree status\n```\n{output}\n```"),
    (["git", "branch", "--show-current"], "Current branch: `{output}`"),
]


def collect_git_context(cwd: str) -> list[str]:
    """Run git commands and collect non-empty output fragments."""
    fragments: list[str] = []
    for cmd, template in GIT_COMMANDS:
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = result.stdout.strip()
        if result.returncode == 0 and output:
            fragments.append(template.format(output=output))
    return fragments


class SessionStartContextRule(Rule):
    """Inject project context on session start."""

    rule_id: str = "SESSION-001"
    title: str = "Session start context injection"
    events: tuple[str, ...] = ("SessionStart",)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        fragments = collect_git_context(str(ctx.cwd))
        if not fragments:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context=(
                    "# Project Context (auto-injected)\n\n" + "\n\n".join(fragments)
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Config change guard
# ---------------------------------------------------------------------------

CONFIG_BLOCKED_SOURCES = (
    "project_settings",
    "local_settings",
    "user_settings",
)


class ConfigChangeGuardRule(Rule):
    """Block config changes that weaken security."""

    rule_id: str = "CONFIG-001"
    title: str = "Config change guard"
    events: tuple[str, ...] = ("ConfigChange",)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        source = string_value(ctx.payload.payload.get("source")) or ""
        if source not in CONFIG_BLOCKED_SOURCES:
            return []
        changes = object_dict(ctx.payload.payload.get("changes"))
        if not changes:
            return []
        if bool_value(changes.get("disableAllHooks")) is True:
            return [
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.CRITICAL,
                    decision="block",
                    message="Disabling all hooks is blocked.",
                    metadata={"source": source},
                )
            ]
        if "hooks" in changes:
            return [
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.HIGH,
                    decision="block",
                    message="Modifying hook config is blocked.",
                    metadata={"source": source},
                )
            ]
        return []
