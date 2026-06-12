"""Rules for enforcing error resolution behavior.

ERRORS-BASH-001: PostToolUse Bash — catches exit-0 commands with error output
ERRORS-FAIL-001: PostToolUseFailure Bash — catches non-zero exit commands

Both inject context telling Claude to fix errors instead of dismissing them.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate._types import object_dict, string_value
from slopgate.constants import METADATA_COMMAND, POST_TOOL_USE
from slopgate.models import RuleFinding, Severity
from slopgate.rules._error_output_signals import has_error_signals
from slopgate.rules.base import Rule
from slopgate.util.payloads import is_shell_tool

if TYPE_CHECKING:
    from slopgate.context import HookContext


# ── Command classification ───────────────────────────────────────────────

# Commands whose output should NEVER trigger error detection
# (read-only / informational — output naturally contains "error" as data)
_READ_ONLY_PREFIXES = (
    "grep ",
    "grep\t",
    "egrep ",
    "fgrep ",
    "rg ",
    "ag ",
    "ack ",
    "cat ",
    "head ",
    "tail ",
    "less ",
    "more ",
    "bat ",
    "ls ",
    "ls\t",
    "ll ",
    "dir ",
    "tree ",
    "du ",
    "df ",
    "wc ",
    "find ",
    "locate ",
    "fd ",
    "git log",
    "git show",
    "git diff",
    "git status",
    "git blame",
    "git branch",
    "git tag",
    "git remote",
    "git stash list",
    "which ",
    "whereis ",
    "type ",
    "file ",
    "stat ",
    "echo ",
    "printf ",
    "env",
    "printenv",
    "man ",
    "help ",
    "pwd",
)

# Start-of-command matchers (the command might have flags before the verb)
_READ_ONLY_PATTERNS = re.compile(
    r"^(?:command\s+-v|type\s+|hash\s+|readlink\s+|realpath\s+|basename\s+|dirname\s+)",
    re.IGNORECASE,
)


def _is_read_only_command(command: str) -> bool:
    """Check if a Bash command is read-only / informational."""
    stripped = command.strip()
    lowered = stripped.lower()

    # Direct prefix match
    for prefix in _READ_ONLY_PREFIXES:
        if lowered.startswith(prefix) or lowered == prefix.strip():
            return True

    # Pattern match
    if _READ_ONLY_PATTERNS.match(lowered):
        return True

    # Piped commands: if the first command is read-only, the whole pipeline is
    first_cmd = stripped.split("|")[0].strip()
    if first_cmd != stripped:
        first_lowered = first_cmd.lower()
        for prefix in _READ_ONLY_PREFIXES:
            if first_lowered.startswith(prefix) or first_lowered == prefix.strip():
                return True

    return False


# Commands where non-zero exit is normal behavior (not an error)
_BENIGN_FAIL_PATTERNS = (
    # grep/rg: exit 1 = no match
    re.compile(r"^(grep|egrep|fgrep|rg|ag|ack)\b", re.IGNORECASE),
    # diff: exit 1 = files differ
    re.compile(r"^diff\b", re.IGNORECASE),
    # test / [ ]: exit 1 = condition false
    re.compile(r"^(test\s|\[\s)", re.IGNORECASE),
    # which / command -v: exit 1 = not found
    re.compile(r"^(which|command\s+-v|type\s+|hash\s+)\b", re.IGNORECASE),
    # git diff --exit-code: exit 1 = changes exist
    re.compile(r"^git\s+diff\b.*--exit-code", re.IGNORECASE),
    # curl with --fail: exit 22 = HTTP error (often used for probing)
    re.compile(r"^curl\b.*--fail", re.IGNORECASE),
)


def _strip_command_wrapper(command: str) -> str:
    stripped = command.strip()
    lowered = stripped.lower()
    if lowered.startswith("rtk "):
        return stripped.split(maxsplit=1)[1].strip()
    return stripped


def _is_benign_failure(command: str) -> bool:
    """Check if a non-zero exit is expected/normal for this command."""
    stripped = _strip_command_wrapper(command)
    for pattern in _BENIGN_FAIL_PATTERNS:
        if pattern.search(stripped):
            return True
    return False


# ── Context message ─────────────────────────────────────────────────────

_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|cookie|authorization)(=|:)\S+"
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")


def _safe_command_excerpt(command: str) -> str:
    """Return a short command excerpt without obvious inline credentials."""
    redacted = _SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED]", command.strip())
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    return redacted[:200]


_ERROR_CONTEXT = (
    "⚠️ ERRORS-BASH-001 — Bash produced error-like output even though the command exited 0.\n"
    "Next action: Rerun the smallest failing command, inspect the reported failure, "
    "and repair it before continuing feature work.",
    "Use the visible stdout/stderr as the repair target.",
    "If the command semantics make non-zero or error-looking text expected, rerun "
    "with an explicit probe command and record that classification.",
)
_QUALITY_COMMAND_CONTEXT = (
    "⚠️ ERRORS-BASH-001 — quality-command output/finding visibility: a lint or quality command exited 0 but printed violation/error-looking findings.\n"
    "Next action: Rerun the full quality command from the repo root without tail-only snippets; use `slopgate lint check --details` when you need exact repair context.",
    "Use the full quality output as the repair target.",
    "Do NOT summarize only the tail output or continue before the full lint/details "
    "view has been inspected.",
)
_FAILURE_CONTEXT = (
    "⚠️ ERRORS-FAIL-001 — Bash command exited non-zero.\n"
    "Next action: Inspect stdout/stderr, fix the root cause, then rerun the same "
    "smallest command to verify.",
    "Use the command output and exit status as the repair target.",
    "If this command has expected non-zero semantics such as grep/rg no-match or "
    "diff differences, rerun with an explicit probe command instead of treating it "
    "as a code failure.",
)


def _command_error_context(command: str, template: tuple[str, str, str]) -> str:
    heading_and_next_action, target_guidance, classification_guidance = template
    excerpt = _safe_command_excerpt(command)
    return (
        f"{heading_and_next_action}\n"
        f"Command: `{excerpt}`\n"
        f"{target_guidance} Fix the issue now, then rerun the same smallest "
        "command to verify.\n"
        f"{classification_guidance}\n"
        "If credentials or an external service block repair, report that "
        "blocker explicitly."
    )


# ── Rules ───────────────────────────────────────────────────────────────


def _extract_bash_output(ctx: HookContext) -> str:
    """Return combined stdout+stderr from a PostToolUse payload, or empty string."""
    tool_response = object_dict(ctx.payload.payload.get("tool_response"))
    if not tool_response:
        return ""
    stdout = string_value(tool_response.get("stdout")) or ""
    stderr = string_value(tool_response.get("stderr")) or ""
    return f"{stdout}\n{stderr}".strip()


def _active_bash_command(ctx: HookContext, rule_id: str) -> str | None:
    enabled = ctx.config.enabled_rules.get(rule_id)
    if enabled is not None and not enabled:
        return None
    if not is_shell_tool(ctx.tool_name):
        return None
    return ctx.shell_command or None


class BashOutputErrorRule(Rule):
    """Detect errors in Bash output even when exit code is 0.

    PostToolUse fires for exit-0 commands. Some tools (ruff --exit-zero,
    eslint --max-warnings, etc.) exit 0 despite reporting errors.
    """

    rule_id: str = "ERRORS-BASH-001"
    title: str = "Bash output error interceptor"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        command = _active_bash_command(ctx, self.rule_id)
        if command is None or _is_read_only_command(command):
            return []
        output = _extract_bash_output(ctx)
        if not output or not has_error_signals(output):
            return []
        quality_command = re.search(
            r"\b(?:slopgate|vfc|isx)\s+lint\s+", command, re.IGNORECASE
        )
        context_template = (
            _QUALITY_COMMAND_CONTEXT if quality_command else _ERROR_CONTEXT
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                additional_context=_command_error_context(command, context_template),
                metadata={METADATA_COMMAND: _safe_command_excerpt(command)},
            )
        ]


class BashFailureReinforcementRule(Rule):
    """Reinforce that non-zero Bash exits must be resolved.

    PostToolUseFailure fires for ANY non-zero exit. We filter out
    commands where non-zero exit is normal (grep, diff, test, etc.).
    """

    rule_id: str = "ERRORS-FAIL-001"
    title: str = "Bash failure reinforcement"
    events: tuple[str, ...] = ("PostToolUseFailure",)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        command = _active_bash_command(ctx, self.rule_id)
        if command is None:
            return []

        # Skip commands where non-zero exit is expected behavior
        if _is_benign_failure(command):
            return []

        # Skip read-only commands that failed (e.g., cat nonexistent_file)
        if _is_read_only_command(command):
            return []

        # Skip interrupted commands
        if ctx.payload.payload.get("is_interrupt", False):
            return []

        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                additional_context=_command_error_context(command, _FAILURE_CONTEXT),
                metadata={METADATA_COMMAND: _safe_command_excerpt(command)},
            )
        ]
