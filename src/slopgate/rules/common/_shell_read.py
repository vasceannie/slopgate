"""Common Slopgate runtime rules."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    DENY,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
    METADATA_PATH,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.path_filters import is_third_party_or_virtualenv_path
from slopgate.util.payloads import (
    is_read_only_tool_use,
    is_shell_tool,
    path_matches_glob,
)

from ._shell_safe_read import is_safe_read_shell_command, shell_tokens

if TYPE_CHECKING:
    from slopgate.context import HookContext

GIT_NO_VERIFY_SHORTCUT = "-n (shorthand for --no-verify)"


def _is_broad_claude_dir_pattern(pattern: str) -> bool:
    normalized_pattern = pattern.strip().lower().replace("\\", "/")
    return normalized_pattern in {".claude/", "*/.claude/"}


def _normalize_claude_candidate_path(path_value: str) -> str:
    normalized_path = path_value.lower().replace("\\", "/")
    while normalized_path.startswith("./"):
        normalized_path = normalized_path[2:]
    return f"/{normalized_path.lstrip('/')}"


def _is_claude_worktree_path(path_value: str) -> bool:
    return "/.claude/worktrees/" in _normalize_claude_candidate_path(path_value)


def _is_claude_plan_markdown_path(path_value: str) -> bool:
    marker = "/.claude/plans/"
    normalized_path = _normalize_claude_candidate_path(path_value)
    if marker not in normalized_path:
        return False
    plan_name = normalized_path.rsplit(marker, 1)[1]
    return bool(plan_name) and "/" not in plan_name and plan_name.endswith(".md")


def path_matches_any(path_value: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if not path_matches_glob(path_value, pattern):
            continue
        if _is_broad_claude_dir_pattern(pattern) and (
            _is_claude_worktree_path(path_value)
            or _is_claude_plan_markdown_path(path_value)
        ):
            continue
        return pattern
    return None


def read_context_fragment(root: Path, relative: str) -> str | None:
    """Read a prompt context file and return its fragment, or None to skip."""
    path = root / relative
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return f"## {relative}\n{content}" if content else None


class PromptContextRule(Rule):
    rule_id: str = "BUILTIN-INJECT-PROMPT"
    title: str = "Inject prompt context"
    events: tuple[str, ...] = ("UserPromptSubmit",)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        fragments = [
            frag
            for relative in ctx.config.prompt_context_files
            if (frag := read_context_fragment(ctx.config.root, relative)) is not None
        ]
        if not fragments:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context="\n\n".join(fragments),
                metadata={"source_files": ctx.config.prompt_context_files},
            )
        ]


def find_read_target(
    paths: list[str],
    exempt: tuple[str, ...],
) -> str | None:
    """Return the candidate read path, or None if exempt."""
    target = None
    for path_value in paths:
        if any(path_value.lower().endswith(s) for s in exempt):
            return None
        target = path_value
    return target


def is_large_file(path_str: str, threshold: int) -> bool:
    try:
        return Path(path_str).stat().st_size > threshold
    except OSError:
        return False


class FullFileReadRule(Rule):
    rule_id: str = "BUILTIN-ENFORCE-FULL-READ"
    title: str = "Enforce full file read"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    EXEMPT_SUFFIXES: tuple[str, ...] = (
        ".md",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".txt",
        ".log",
        ".csv",
    )
    LARGE_FILE_BYTES: int = 40_000

    @staticmethod
    def _normalize_read_path(ctx: "HookContext", target: str) -> str:
        path = Path(target)
        if not path.is_absolute():
            path = ctx.cwd / path
        return str(path.resolve(strict=False))

    @staticmethod
    def _is_full_read(tool_input: Mapping[str, object]) -> bool:
        return "offset" not in tool_input and "limit" not in tool_input

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if ctx.tool_name != "Read":
            return []
        target = find_read_target(ctx.candidate_paths, self.EXEMPT_SUFFIXES)
        if target is None:
            return []
        if is_third_party_or_virtualenv_path(target):
            return []
        normalized_target = self._normalize_read_path(ctx, target)
        if self._is_full_read(ctx.tool_input):
            ctx.state.record_full_read(ctx.session_id, normalized_target)
            return []
        if ctx.state.has_full_read(ctx.session_id, normalized_target):
            return []
        if is_large_file(normalized_target, self.LARGE_FILE_BYTES):
            return []
        msg = (
            f"Please read `{target}` in full first "
            f"(no offset/limit). Partial reads are blocked "
            f"for initial inspection."
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.MEDIUM,
                decision=DENY,
                message=msg,
                metadata={METADATA_PATH: normalized_target, "target": "tool_input"},
            )
        ]


def is_safe_bash_read(tool_name: str | None, bash_command: str | None) -> bool:
    return (
        tool_name is not None
        and is_shell_tool(tool_name)
        and bash_command is not None
        and is_safe_read_shell_command(bash_command, reject_find_mutation=True)
    )


def _is_sed_transform(tool_name: str | None, bash_command: str | None) -> bool:
    if tool_name is None or bash_command is None or not is_shell_tool(tool_name):
        return False
    tokens = shell_tokens(bash_command)
    is_sed = bool(tokens) and Path(tokens[0].strip("\"'")).name.lower() == "sed"
    return is_sed and (not is_safe_bash_read(tool_name, bash_command))


def find_matched_protected_path(
    candidate_paths: list[str],
    patterns: list[str],
) -> str | None:
    for path_value in candidate_paths:
        if path_matches_any(path_value, patterns):
            return path_value
    return None


def _is_makefile_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] == "Makefile"


def _is_makefile_target_execution(
    tool_name: str | None, bash_command: str | None
) -> bool:
    if tool_name is None or bash_command is None or not is_shell_tool(tool_name):
        return False
    tokens = shell_tokens(bash_command)
    return bool(tokens) and Path(tokens[0]).name == "make"


def _protected_path_decision(matched_path: str) -> str:
    if _is_makefile_path(matched_path):
        return "ask"
    return DENY


class ProtectedPathsRule(Rule):
    rule_id: str = "BUILTIN-PROTECTED-PATHS"
    title: str = "Protected paths"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        patterns = ctx.config.protected_paths
        if not patterns:
            return []
        if is_read_only_tool_use(ctx):
            return []
        if not ctx.mutating and not _is_sed_transform(
            ctx.tool_name,
            ctx.shell_command,
        ):
            return []
        matched_path = find_matched_protected_path(ctx.candidate_paths, patterns)
        if matched_path is None:
            return []
        if is_safe_bash_read(ctx.tool_name, ctx.shell_command):
            return []
        if _is_makefile_path(matched_path) and _is_makefile_target_execution(
            ctx.tool_name,
            ctx.shell_command,
        ):
            return []
        decision = _protected_path_decision(matched_path)
        message = (
            f"Protected path matched: {matched_path}. "
            "Read-only inspection and `make <target>` execution are allowed for "
            "Makefiles; content changes require explicit approval."
            if decision == "ask"
            else (
                f"Protected path matched: {matched_path}. "
                f"Modify configuration only with explicit "
                f"approval or move the check into config.json."
            )
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision,
                message=message,
                metadata={METADATA_PATH: matched_path},
            )
        ]
