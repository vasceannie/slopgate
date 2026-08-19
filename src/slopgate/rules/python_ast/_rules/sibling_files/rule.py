"""Block package splits that create flat prefix_* sibling modules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import (
    BLOCK,
    DENY,
    METADATA_PATH,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.path_filters import is_authored_python_path
from slopgate.util.payloads import is_bash_tool, is_edit_like_tool, is_mutating_tool_use

from .groups import (
    build_pkg_block,
    has_same_named_package,
    prefix_groups,
    sibling_group_message,
)
from .paths import FlatSiblingFindingInput, prefix_for_name
from .patch import flat_sibling_projected_removed_files
from .paths import flat_sibling_resolve_candidate_path

if TYPE_CHECKING:
    from slopgate.context import HookContext


@final
class PythonFlatFileSiblingsRule(Rule):
    """Block package splits that create flat sibling modules instead of packages.

    The original guard only caught ``_prefix_*.py`` files after a write. That
    missed the more common ``prefix_*.py`` shape (``result_models.py``,
    ``result_runner.py``) and files that sit beside an already-created package
    directory (``context_models.py`` next to ``context/``). Those are both
    strong signs the split should be ``prefix/__init__.py`` plus focused child
    modules.
    """

    rule_id = "PY-CODE-017"
    title = "Block flat prefix_* sibling file sprawl"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)
    _MIN_SIBLINGS = 3
    prefix_for_name = staticmethod(prefix_for_name)

    def _finding_for_group(self, group: FlatSiblingFindingInput) -> RuleFinding:
        """Return one finding for a clustered prefix_* sibling group."""
        sorted_files = sorted(group.files)
        files_str = ", ".join(sorted_files[:5])
        pkg_block = build_pkg_block(group.files, group.prefix)
        representative_path = (
            str(group.parent / sorted_files[0]) if sorted_files else str(group.parent)
        )
        header = sibling_group_message(
            group.parent.name, group.prefix, files_str, group.reason
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=group.decision,
            message=(
                f"{header}\n{pkg_block}\n\nThe __init__.py should re-export "
                "so external imports don't change."
            ),
            metadata={
                METADATA_PATH: representative_path,
                "directory": str(group.parent),
                "prefix": group.prefix,
                "count": len(group.files),
                "files": sorted_files,
                "reason": group.reason,
            },
        )

    def _findings_for_directory(
        self,
        parent: Path,
        extra_files: set[str],
        decision: str,
        removed_files: set[str] | None = None,
    ) -> list[RuleFinding]:
        """Return findings for one directory's projected sibling groups."""
        findings: list[RuleFinding] = []
        projected_removed_files = removed_files or set()
        for prefix, files in prefix_groups(
            parent, extra_files, projected_removed_files
        ).items():
            has_package = has_same_named_package(parent, prefix)
            if has_package:
                findings.append(
                    self._finding_for_group(
                        FlatSiblingFindingInput(
                            parent,
                            prefix,
                            files,
                            decision,
                            f"`{prefix}/` already exists",
                        )
                    )
                )
            elif len(files) >= self._MIN_SIBLINGS:
                findings.append(
                    self._finding_for_group(
                        FlatSiblingFindingInput(
                            parent,
                            prefix,
                            files,
                            decision,
                            f"{len(files)} files share the `{prefix}` prefix",
                        )
                    )
                )
        return findings

    def _resolve_candidate_dirs(self, ctx: HookContext) -> dict[Path, set[str]]:
        """Collect candidate parent directories and projected filenames."""
        dirs: dict[Path, set[str]] = {}
        for path_value in ctx.candidate_paths:
            if not is_authored_python_path(path_value):
                continue
            full = flat_sibling_resolve_candidate_path(ctx, path_value)
            parent = full.parent
            if parent.exists() and parent.is_dir():
                files = dirs.setdefault(parent, set())
                if ctx.event_name != POST_TOOL_USE or full.exists():
                    files.add(full.name)
        return dirs

    @staticmethod
    def _should_evaluate(ctx: HookContext) -> bool:
        """Evaluate proactive writes, but let Bash filesystem moves reach post-check.

        A package-split repair may need a mechanical `mkdir`/`mv` batch while the
        old flat siblings still exist. Blocking Bash before that batch executes
        traps agents in a repeated-deny loop. PostToolUse still verifies the
        resulting filesystem shape, and PY-SHELL-001 continues to block shell
        edits to Python source.
        """
        if ctx.event_name in {PRE_TOOL_USE, PERMISSION_REQUEST}:
            return is_edit_like_tool(ctx.tool_name)
        if ctx.event_name == POST_TOOL_USE:
            return is_edit_like_tool(ctx.tool_name) or (
                is_bash_tool(ctx.tool_name) and is_mutating_tool_use(ctx)
            )
        return False

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if ctx.event_name not in self.events:
            return []
        if not self._should_evaluate(ctx):
            return []
        decision = (
            DENY if ctx.event_name in {PRE_TOOL_USE, PERMISSION_REQUEST} else BLOCK
        )
        findings: list[RuleFinding] = []
        removed_by_parent = flat_sibling_projected_removed_files(ctx)
        for parent, extra_files in self._resolve_candidate_dirs(ctx).items():
            findings.extend(
                self._findings_for_directory(
                    parent, extra_files, decision, removed_by_parent.get(parent)
                )
            )
        return findings
