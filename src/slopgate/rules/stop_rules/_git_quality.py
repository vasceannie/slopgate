"""Stop/session runtime rules."""

from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast
from typing_extensions import override
from slopgate.constants import PERMISSION_REQUEST, PRE_TOOL_USE, METADATA_PATH
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

if TYPE_CHECKING:
    from slopgate.context import HookContext
TAIL_BYTES = 32768
SLOPGATE_REPO_SUFFIX = "/claude/slopgate"


def resolve_candidate_path(path_str: str, cwd: Path | None = None) -> Path:
    """Resolve a candidate path relative to the hook cwd when needed."""
    path = Path(path_str).expanduser()
    if not path.is_absolute() and cwd is not None:
        path = cwd / path
    return path.resolve()


def git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    """Run a git command and return stripped stdout on success."""
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def git_repo_root(path_str: str, cwd: Path | None = None) -> Path | None:
    """Return the git toplevel containing *path_str*, if any."""
    resolved = resolve_candidate_path(path_str, cwd)
    base = resolved if resolved.is_dir() else resolved.parent
    repo_root = git_output(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"], timeout=3
    )
    return Path(repo_root) if repo_root else None


def normalize_git_remote(url: str) -> str:
    """Normalize a git remote for comparison."""
    raw = url.strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    ssh_match = re.match("^git@([^:]+):(.+)$", raw)
    if ssh_match:
        host = ssh_match.group(1).lower()
        path = ssh_match.group(2).strip("/")
        return f"{host}/{path}"
    proto_match = re.match("^[a-z]+://([^/]+)/(.+)$", raw, re.IGNORECASE)
    if proto_match:
        host = proto_match.group(1).lower()
        path = proto_match.group(2).strip("/")
        return f"{host}/{path}"
    return raw.lower()


def is_worktree(path_str: str, cwd: Path | None = None) -> bool:
    """Check if a path is inside a git worktree (not the main working tree).

    A worktree has a .git *file* (not directory) containing "gitdir: ..." pointing
    back to the main repo's .git/worktrees/<name>/ directory.
    """
    repo_root = git_repo_root(path_str, cwd)
    if repo_root is None:
        return False
    git_entry = repo_root / ".git"
    return git_entry.is_file()


def is_slopgate_repo(path_str: str, cwd: Path | None = None) -> bool:
    """Return True when the target path belongs to the slopgate repo."""
    repo_root = git_repo_root(path_str, cwd)
    if repo_root is None:
        return False
    remote = git_output(
        ["git", "-C", str(repo_root), "remote", "get-url", "origin"], timeout=5
    )
    if remote is None:
        return False
    normalized = normalize_git_remote(remote)
    return normalized.endswith(SLOPGATE_REPO_SUFFIX)


def default_branch_name(repo_root: Path) -> str | None:
    """Infer the repository default branch name."""
    remote_head = git_output(
        ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
        timeout=5,
    )
    if remote_head and remote_head.startswith("refs/remotes/origin/"):
        return remote_head.rsplit("/", 1)[-1]
    local_heads = git_output(
        [
            "git",
            "-C",
            str(repo_root),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        ],
        timeout=5,
    )
    if not local_heads:
        return None
    branches = {branch.strip() for branch in local_heads.splitlines() if branch.strip()}
    if "main" in branches:
        return "main"
    if "master" in branches:
        return "master"
    if len(branches) == 1:
        return next(iter(branches))
    return None


def is_non_default_branch(path_str: str, cwd: Path | None = None) -> bool:
    """Return True when the target path is on a branch other than the default."""
    repo_root = git_repo_root(path_str, cwd)
    if repo_root is None:
        return False
    current_branch = git_output(
        ["git", "-C", str(repo_root), "branch", "--show-current"], timeout=5
    )
    default_branch = default_branch_name(repo_root)
    return bool(
        current_branch and default_branch and (current_branch != default_branch)
    )


def tail_read(file_path: Path, num_bytes: int) -> str:
    """Read the last *num_bytes* of a file as UTF-8 text."""
    with open(file_path, "rb") as fh:
        try:
            _ = fh.seek(-num_bytes, 2)
        except OSError:
            _ = fh.seek(0)
        return fh.read().decode("utf-8", errors="replace")


def extract_content_text(msg: object) -> str:
    """Extract text from an assistant message content field."""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        blocks = cast(list[object], msg)
        extracted: list[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            typed_block = cast(dict[str, object], block)
            raw_type = typed_block.get("type")
            if not isinstance(raw_type, str) or raw_type != "text":
                continue
            raw_text = typed_block.get("text")
            if isinstance(raw_text, str):
                extracted.append(raw_text)
        return " ".join(extracted)
    return ""


def last_assistant_response(transcript_path: str) -> str:
    """Read the last assistant turn from a Claude Code JSONL transcript."""
    tp = Path(transcript_path)
    if not tp.exists():
        return ""
    try:
        tail = tail_read(tp, TAIL_BYTES)
    except OSError:
        return ""
    for line in reversed(tail.strip().splitlines()[-20:]):
        try:
            raw_entry: object = cast(object, json.loads(line))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, object], raw_entry)
        raw_type = entry.get("type")
        raw_role_field = entry.get("role")
        raw_role: object = raw_type if raw_type is not None else raw_role_field
        if not isinstance(raw_role, str) or raw_role != "assistant":
            continue
        raw_msg_container = entry.get("message")
        if not isinstance(raw_msg_container, dict):
            continue
        msg_container = cast(dict[str, object], raw_msg_container)
        msg: object = msg_container.get("content", "")
        return extract_content_text(msg)
    return ""


def get_stop_response(ctx: HookContext) -> str:
    """Extract the assistant response from a Stop/SubagentStop event."""
    transcript_path = ctx.payload.payload.get("transcript_path", "")
    if isinstance(transcript_path, str) and transcript_path:
        response = last_assistant_response(transcript_path)
        if response:
            return response
    fallback = ctx.payload.payload.get("stop_response", "")
    return str(fallback) if fallback else ""


PREEXISTING_PHRASES = (
    "pre-existing",
    "preexisting",
    "already existed",
    "was already",
    "existed before",
    "not introduced by",
    "outside the scope",
    "out of scope",
    "not my change",
)


class IgnorePreexistingRule(Rule):
    """Block responses that dismiss issues as pre-existing."""

    rule_id: str = "STOP-001"
    title: str = "Block ignoring pre-existing issues"
    events: tuple[str, ...] = ("Stop", "SubagentStop")

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        response = get_stop_response(ctx)
        if not response:
            return []
        lowered = response.lower()
        for phrase in PREEXISTING_PHRASES:
            if phrase in lowered:
                return [
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.HIGH,
                        decision="block",
                        message="Do not dismiss issues as pre-existing. If you found a problem, fix it or explicitly flag it for follow-up.",
                        metadata={"matched_phrase": phrase},
                    )
                ]
        return []


DEFERRED_TEST_INTEGRITY_COMMAND = "slopgate lint test-integrity"
QUALITY_REMINDER = (
    "Before stopping, run quality check `{command}` or report exactly why it cannot run. "
    f"Deferred suite-wide test-integrity collectors run through `{DEFERRED_TEST_INTEGRITY_COMMAND}`."
)


class RequireQualityCheckRule(Rule):
    """Remind to run quality gate before stopping."""

    rule_id: str = "STOP-002"
    title: str = "Require quality check reminder"
    events: tuple[str, ...] = ("Stop", "SubagentStop")

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.state.should_emit_stop_quality_reminder(ctx.session_id):
            return []
        response = get_stop_response(ctx).lower()
        if any((phrase in response for phrase in PREEXISTING_PHRASES)):
            return []
        ctx.state.record_stop_quality_reminder(ctx.session_id)
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context=QUALITY_REMINDER.format(
                    command=ctx.config.hook_quality_check_command
                ),
            )
        ]


class WarnLargeFileRule(Rule):
    """Warn when editing files that are suspiciously large."""

    rule_id: str = "WARN-LARGE-001"
    title: str = "Warn on large file"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)
    MAX_CHARS: int = 50000

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        findings: list[RuleFinding] = []
        for target in ctx.content_targets:
            char_count = len(target.content)
            if char_count > self.MAX_CHARS:
                message = (
                    f"WARNING: File {target.path} content is {char_count:,} characters. "
                    "Consider splitting into smaller modules."
                )
                findings.append(
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.MEDIUM,
                        additional_context=message,
                        metadata={METADATA_PATH: target.path, "chars": char_count},
                    )
                )
        return findings
