"""Python AST runtime rules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, final
from typing_extensions import override
from vibeforcer.constants import (
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    BLOCK,
    METADATA_PATH,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.util.path_filters import is_third_party_or_virtualenv_path
from vibeforcer.util.payloads import (
    first_present,
    is_bash_tool,
    is_edit_like_tool,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext


class _FlatSiblingFindingInput(NamedTuple):
    parent: Path
    prefix: str
    files: list[str]
    decision: str
    reason: str


def _flat_sibling_resolve_candidate_path(ctx: HookContext, path_value: str) -> Path:
    raw_path = Path(path_value)
    return raw_path if raw_path.is_absolute() else (Path(ctx.cwd) / raw_path).resolve()


def _flat_sibling_patch_blob(ctx: HookContext) -> str:
    return first_present(ctx.tool_input, ("patch", "patchText", "patch_text"))


def _flat_sibling_patch_added_and_removed_paths(
    patch_blob: str,
) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    current_update_path = ""
    for line in patch_blob.splitlines():
        if line.startswith("*** Update File: "):
            current_update_path = line.replace("*** Update File: ", "", 1).strip()
            continue
        if line.startswith("*** Add File: "):
            added.append(line.replace("*** Add File: ", "", 1).strip())
            current_update_path = ""
            continue
        if line.startswith("*** Delete File: "):
            removed.append(line.replace("*** Delete File: ", "", 1).strip())
            current_update_path = ""
            continue
        if line.startswith("*** Move to: "):
            if current_update_path:
                removed.append(current_update_path)
            added.append(line.replace("*** Move to: ", "", 1).strip())
            current_update_path = ""
    return added, removed


def _flat_sibling_projected_removed_files(ctx: HookContext) -> dict[Path, set[str]]:
    """Return flat sibling filenames a patch is deleting/moving away."""
    patch_blob = _flat_sibling_patch_blob(ctx)
    if not patch_blob:
        return {}
    _, removed_paths = _flat_sibling_patch_added_and_removed_paths(patch_blob)
    removed_by_parent: dict[Path, set[str]] = {}
    for path_value in removed_paths:
        if not path_value.lower().endswith((".py", ".pyi")):
            continue
        if is_third_party_or_virtualenv_path(path_value):
            continue
        full = _flat_sibling_resolve_candidate_path(ctx, path_value)
        prefix = PythonFlatFileSiblingsRule.prefix_for_name(full.name)
        if prefix is None:
            continue
        removed_by_parent.setdefault(full.parent, set()).add(full.name)
    return removed_by_parent


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
    _IGNORED_PREFIXES = frozenset({"test"})

    @staticmethod
    def prefix_for_name(name: str) -> str | None:
        """Return the package prefix for prefix_*.py and _prefix_*.py names."""
        import re as _re

        match = _re.match(r"^_?([a-z][a-z0-9]*)_[a-z0-9_]+\.pyi?$", name)
        if match is None:
            return None
        prefix = match.group(1)
        if prefix in PythonFlatFileSiblingsRule._IGNORED_PREFIXES:
            return None
        return prefix

    @staticmethod
    def _prefix_groups(
        directory: Path, extra_files: set[str], removed_files: set[str]
    ) -> dict[str, list[str]]:
        """Group existing plus projected sibling files by shared package prefix."""
        groups: dict[str, list[str]] = {}
        names = set(extra_files)
        if directory.exists():
            for child in directory.iterdir():
                if child.is_file():
                    names.add(child.name)
        names.difference_update(removed_files)
        for name in names:
            prefix = PythonFlatFileSiblingsRule.prefix_for_name(name)
            if prefix is not None:
                groups.setdefault(prefix, []).append(name)
        return groups

    @staticmethod
    def _module_name_for_package(files: list[str], prefix: str) -> list[str]:
        modules: list[str] = []
        for name in sorted(files)[:5]:
            stem = name.removesuffix(".pyi").removesuffix(".py")
            for tag in (f"_{prefix}_", f"{prefix}_"):
                if stem.startswith(tag):
                    stem = stem.removeprefix(tag)
                    break
            modules.append(f"{stem}.py")
        return modules

    @classmethod
    def _build_pkg_block(cls, files: list[str], prefix: str) -> str:
        """Return indented child-module lines for the suggested package layout."""
        return "\n".join(
            "        " + module for module in cls._module_name_for_package(files, prefix)
        )

    @staticmethod
    def _has_same_named_package(parent: Path, prefix: str) -> bool:
        package = parent / prefix
        return package.is_dir() and (package / "__init__.py").exists()

    def _finding_for_group(self, group: _FlatSiblingFindingInput) -> RuleFinding:
        sorted_files = sorted(group.files)
        files_str = ", ".join(sorted_files[:5])
        pkg_block = self._build_pkg_block(group.files, group.prefix)
        representative_path = str(group.parent / sorted_files[0]) if sorted_files else str(group.parent)
        nl = "\n"
        msg = (
            f"Directory `{group.parent.name}/` has flat `{group.prefix}_*.py` "
            f"sibling modules ({files_str}); {group.reason}. "
            f"Convert to a sub-package instead:{nl}{nl}"
            f"    {group.parent.name}/{group.prefix}/{nl}"
            f"        __init__.py   (re-export public API){nl}"
            f"{pkg_block}{nl}{nl}"
            f"The __init__.py should re-export so external imports don't change."
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=group.decision,
            message=msg,
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
        findings: list[RuleFinding] = []
        projected_removed_files = removed_files or set()
        for prefix, files in self._prefix_groups(
            parent, extra_files, projected_removed_files
        ).items():
            has_package = self._has_same_named_package(parent, prefix)
            if has_package:
                findings.append(
                    self._finding_for_group(
                        _FlatSiblingFindingInput(
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
                        _FlatSiblingFindingInput(
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
        dirs: dict[Path, set[str]] = {}
        for path_value in ctx.candidate_paths:
            if not path_value.lower().endswith((".py", ".pyi")):
                continue
            if is_third_party_or_virtualenv_path(path_value):
                continue
            full = _flat_sibling_resolve_candidate_path(ctx, path_value)
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
            return is_edit_like_tool(ctx.tool_name) or is_bash_tool(ctx.tool_name)
        return False

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if ctx.event_name not in self.events:
            return []
        if not self._should_evaluate(ctx):
            return []
        decision = DENY if ctx.event_name in {PRE_TOOL_USE, PERMISSION_REQUEST} else BLOCK
        findings: list[RuleFinding] = []
        removed_by_parent = _flat_sibling_projected_removed_files(ctx)
        for parent, extra_files in self._resolve_candidate_dirs(ctx).items():
            findings.extend(
                self._findings_for_directory(
                    parent,
                    extra_files,
                    decision,
                    removed_by_parent.get(parent),
                )
            )
        return findings
