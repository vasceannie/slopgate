"""Stop/session runtime rules."""

from __future__ import annotations
import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import DENY, PERMISSION_REQUEST, PRE_TOOL_USE, METADATA_PATH
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ._infra_security import is_modifying_tool, is_safe_bash_for_path

ENROLLMENT_SENTINELS = frozenset({".noslopgate", ".no-slop-gate"})
ENROLLMENT_MARKER = "slopgate.toml"
QUALITY_GATE_DISABLE_RE = re.compile("\\benabled\\s*=\\s*false\\b", re.IGNORECASE)


def enrollment_basename(path_value: str) -> str:
    basename = Path(path_value).name
    return basename.lower()


def is_delete_like_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return lowered in {"delete", "remove"}


def patch_touches_enrollment_marker(ctx: HookContext) -> bool:
    patch_blob = ctx.tool_input.get("patch")
    if not isinstance(patch_blob, str):
        return False
    lowered = patch_blob.lower()
    if ENROLLMENT_MARKER not in lowered:
        return False
    return any(
        (
            marker in lowered
            for marker in ("*** add file:", "*** update file:", "*** delete file:")
        )
    )


def repo_enrollment_sentinel_finding(path_value: str) -> RuleFinding | None:
    if enrollment_basename(path_value) not in ENROLLMENT_SENTINELS:
        return None
    return RuleFinding(
        rule_id="REPO-ENROLL-001",
        title="Repo enrollment protection",
        severity=Severity.CRITICAL,
        decision=DENY,
        message=f"Creating or modifying quality-gate disable sentinels is blocked in {path_value}.",
        metadata={METADATA_PATH: path_value, "kind": "disable_sentinel"},
    )


def repo_enrollment_marker_finding(
    path_value: str, tool_name: str
) -> RuleFinding | None:
    if enrollment_basename(path_value) != ENROLLMENT_MARKER:
        return None
    if is_delete_like_tool(tool_name):
        return RuleFinding(
            rule_id="REPO-ENROLL-001",
            title="Repo enrollment protection",
            severity=Severity.CRITICAL,
            decision=DENY,
            message=f"Deleting {path_value} would de-enroll the repo and is blocked.",
            metadata={METADATA_PATH: path_value, "kind": "delete_marker"},
        )
    if tool_name == "bash":
        return RuleFinding(
            rule_id="REPO-ENROLL-001",
            title="Repo enrollment protection",
            severity=Severity.HIGH,
            decision=DENY,
            message=f"Shell-based edits to {path_value} are blocked. Use structured config changes that keep the repo enrolled.",
            metadata={METADATA_PATH: path_value, "kind": "shell_edit_marker"},
        )
    return RuleFinding(
        rule_id="REPO-ENROLL-001",
        title="Repo enrollment protection",
        severity=Severity.HIGH,
        decision=DENY,
        message=f"Direct edits to {path_value} are blocked. Do not relax quality gates to make lint pass; fix the code or use a human-reviewed config migration.",
        metadata={METADATA_PATH: path_value, "kind": "direct_edit_marker"},
    )


def repo_enrollment_patch_finding(ctx: HookContext) -> RuleFinding | None:
    if not patch_touches_enrollment_marker(ctx):
        return None
    return RuleFinding(
        rule_id="REPO-ENROLL-001",
        title="Repo enrollment protection",
        severity=Severity.HIGH,
        decision=DENY,
        message="Patch edits to slopgate.toml are blocked. Do not relax quality gates to make lint pass; fix the code or use a human-reviewed config migration.",
        metadata={"kind": "patch_touch_marker"},
    )


def repo_enrollment_content_finding(
    target_path: str, content: str
) -> RuleFinding | None:
    if enrollment_basename(target_path) != ENROLLMENT_MARKER:
        return None
    if QUALITY_GATE_DISABLE_RE.search(content):
        return RuleFinding(
            rule_id="REPO-ENROLL-001",
            title="Repo enrollment protection",
            severity=Severity.CRITICAL,
            decision=DENY,
            message=f"Setting `enabled = false` in {target_path} is blocked. Enrolled repos cannot be de-enrolled by agent edits.",
            metadata={METADATA_PATH: target_path, "kind": "disable_flag"},
        )
    return RuleFinding(
        rule_id="REPO-ENROLL-001",
        title="Repo enrollment protection",
        severity=Severity.HIGH,
        decision=DENY,
        message=f"Direct edits to {target_path} are blocked. Do not relax quality gates to make lint pass; fix the code or use a human-reviewed config migration.",
        metadata={METADATA_PATH: target_path, "kind": "direct_content_marker"},
    )


class RepoEnrollmentProtectionRule(Rule):
    """Prevent agents from weakening or removing repo enrollment."""

    rule_id: str = "REPO-ENROLL-001"
    title: str = "Repo enrollment protection"
    events: tuple[str, ...] = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if is_safe_bash_for_path(ctx):
            return []
        tool_name = ctx.tool_name.lower()
        if not (is_modifying_tool(ctx) or is_delete_like_tool(tool_name)):
            return []
        for path_value in ctx.candidate_paths:
            finding = repo_enrollment_sentinel_finding(path_value)
            if finding is not None:
                return [finding]
            finding = repo_enrollment_marker_finding(path_value, tool_name)
            if finding is not None:
                return [finding]
        finding = repo_enrollment_patch_finding(ctx)
        if finding is not None:
            return [finding]
        for target in ctx.content_targets:
            finding = repo_enrollment_content_finding(target.path, target.content)
            if finding is not None:
                return [finding]
        return []
