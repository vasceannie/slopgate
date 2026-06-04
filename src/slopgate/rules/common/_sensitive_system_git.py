"""Common Slopgate runtime rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    DENY,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
    METADATA_COMMAND,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import (
    lower_path,
    shell_command_executable_paths,
)
from slopgate.util.platform import resolve_path_for_match
if TYPE_CHECKING:
    from slopgate.context import HookContext

from ._shell_read import _GIT_NO_VERIFY_SHORTCUT as _GIT_NO_VERIFY_SHORTCUT, _shell_tokens as _shell_tokens


_META_CHARS = frozenset("[](){}*+?|^$\\")

_compiled_sensitive_cache: dict[tuple[str, ...], list[re.Pattern[str]]] = {}


def _sensitive_pattern_expr(pattern: str) -> str:
    """Return a regex expression for a configured sensitive path pattern."""
    if pattern in {".key", ".pem"}:
        return re.escape(pattern) + r"(?=$|[^a-z0-9_])"
    has_meta = any(ch in _META_CHARS for ch in pattern)
    return pattern if has_meta else re.escape(pattern)


def _compile_sensitive_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    """Compile sensitive path patterns into regexes (cached).

    Plain substring patterns are auto-escaped; patterns containing
    regex metacharacters are compiled as-is.
    """
    cache_key = tuple(raw)
    cached = _compiled_sensitive_cache.get(cache_key)
    if cached is not None:
        return cached
    compiled: list[re.Pattern[str]] = []
    for raw_pattern in raw:
        stripped = raw_pattern.strip()
        if not stripped:
            continue
        expr = _sensitive_pattern_expr(stripped)
        compiled.append(re.compile(expr, re.IGNORECASE))
    _compiled_sensitive_cache[cache_key] = compiled
    return compiled


class SensitiveDataRule(Rule):
    rule_id: str = "GLOBAL-BUILTIN-SENSITIVE-DATA"
    title: str = "Sensitive data protection"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    SAFE_SUFFIXES: tuple[str, ...] = (
        ".example",
        ".sample",
        ".template",
        ".defaults",
        ".dist",
        ".test",
        ".bak",
    )

    def _is_safe_path(self, path_value: str) -> bool:
        """Return True if the path ends with a safe suffix."""
        lowered = lower_path(path_value)
        return any(lowered.endswith(s) for s in self.SAFE_SUFFIXES)

    def _match_in_paths(
        self,
        paths: list[str],
        compiled: list[re.Pattern[str]],
    ) -> str | None:
        """Return first path matching a sensitive pattern, or None."""
        for path_value in paths:
            if self._is_safe_path(path_value):
                continue
            lowered = lower_path(path_value)
            if any(p.search(lowered) for p in compiled):
                return path_value
        return None

    def _match_in_command(
        self,
        command: str,
        compiled: list[re.Pattern[str]],
    ) -> str | None:
        """Return '[command]' if command contains a sensitive match."""
        lowered = command.lower()
        _WORD_BREAKS = frozenset(" \t\n;|&><")
        for pattern in compiled:
            for m in pattern.finditer(lowered):
                rest = lowered[m.end() :]
                end = next(
                    (i for i, ch in enumerate(rest) if ch in _WORD_BREAKS),
                    len(rest),
                )
                tail = rest[:end]
                is_safe = any(
                    tail.startswith(s) or tail == s.lstrip(".")
                    for s in self.SAFE_SUFFIXES
                )
                if not is_safe:
                    return "[command]"
        return None

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        compiled = _compile_sensitive_patterns(
            ctx.config.sensitive_path_patterns,
        )
        if not compiled:
            return []
        matched = self._match_in_paths(ctx.candidate_paths, compiled)
        if not matched and ctx.shell_command:
            matched = self._match_in_command(ctx.shell_command, compiled)
        if not matched:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=DENY,
                message=f"Sensitive data access is blocked: {matched}",
                metadata={"target": matched},
            )
        ]


def _is_exact_dev_null(path_value: str) -> bool:
    """Return True only for the harmless null device path."""
    return lower_path(path_value) == "/dev/null"


def _match_system_path(paths: list[str], prefixes: list[str], cwd: Path) -> str | None:
    """Return the first path matching a system prefix, or None."""
    for path_value in paths:
        lowered = resolve_path_for_match(path_value, cwd)
        if _is_exact_dev_null(lowered):
            continue
        if any(lowered.startswith(p) for p in prefixes):
            return path_value
    return None


def _match_system_command(command: str, prefixes: list[str]) -> str | None:
    """Return '[command]' if command references a system path as a target."""
    lowered = command.lower()
    executable_paths = {lower_path(value) for value in shell_command_executable_paths(command)}
    separator = r"(?:^|[\s;|&(<>=])"
    terminator = r"[^\s;|&()<>'\"]*"
    for prefix in prefixes:
        normalized_prefix = prefix.replace("\\", "/")
        if not normalized_prefix.startswith("/") and not re.match(r"^[a-z]:/", normalized_prefix):
            if prefix in lowered:
                return "[command]"
            continue
        pat = separator + "(" + re.escape(normalized_prefix) + terminator + ")"
        for match in re.finditer(pat, lowered):
            matched_path = match.group(1)
            if _is_exact_dev_null(matched_path):
                continue
            if lower_path(matched_path) in executable_paths:
                continue
            return "[command]"
    return None


class SystemProtectionRule(Rule):
    rule_id: str = "GLOBAL-BUILTIN-SYSTEM-PROTECTION"
    title: str = "System path protection"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        prefixes = [i.replace("\\", "/").lower() for i in ctx.config.system_path_prefixes]
        if not prefixes:
            return []
        matched = _match_system_path(ctx.candidate_paths, prefixes, ctx.cwd)
        if not matched and ctx.shell_command:
            matched = _match_system_command(ctx.shell_command, prefixes)
        if not matched:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.CRITICAL,
                decision=DENY,
                message=(f"Critical system path access is blocked: {matched}"),
                metadata={"target": matched},
            )
        ]


def _is_git_commit_command(tokens: list[str]) -> bool:
    return len(tokens) >= 2 and tokens[:2] == ["git", "commit"]


def _is_git_no_verify_shortcut(token: str) -> bool:
    return token == "-n" or (
        token.startswith("-")
        and not token.startswith("--")
        and "n" in token[1:]
    )


def _detect_git_bypass(command: str) -> str | None:
    """Return bypass type string, or None if no bypass detected."""
    lowered = command.lower()
    git_cmds = ("git commit", "git push", "git merge")
    if "--no-verify" in lowered and any(k in lowered for k in git_cmds):
        return "--no-verify"
    tokens = _shell_tokens(lowered)
    if _is_git_commit_command(tokens) and any(
        _is_git_no_verify_shortcut(token) for token in tokens[2:]
    ):
        return _GIT_NO_VERIFY_SHORTCUT
    if "core.hookspath" in lowered and ("/dev/null" in lowered or "nul" in lowered):
        return "core.hookspath disabled"
    return None


class GitNoVerifyRule(Rule):
    rule_id: str = "GIT-001"
    title: str = "Block git --no-verify"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.shell_command:
            return []
        bypass = _detect_git_bypass(ctx.shell_command)
        if not bypass:
            return []
        msg = (
            f"Git hook bypass detected: `{bypass}`. "
            "Pre-commit and pre-push hooks exist for a "
            "reason — they run linters, type checks, and "
            "tests.\n\nIf hooks are failing, fix the issues "
            "they found rather than skipping them. Next step: run the hook/quality "
            "command normally, keep the full error visible, fix the hook/test failure, "
            "then commit without bypass: `git commit -m <message>`."
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=DENY,
                message=msg,
                metadata={
                    "bypass_type": bypass,
                    METADATA_COMMAND: ctx.shell_command[:200],
                },
            )
        ]
