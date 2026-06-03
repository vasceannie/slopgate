"""Python AST runtime rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, final
from typing_extensions import override
from vibeforcer._types import ObjectDict, object_dict, object_list
from vibeforcer.constants import (
    LINT_MAX_MODULE_LINES_HARD,
    LINT_MAX_MODULE_LINES_SOFT,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
    METADATA_PATH,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule
from vibeforcer.util.path_filters import is_third_party_or_virtualenv_path
from vibeforcer.util.payloads import (
    extract_path_from_mapping,
    first_present,
    is_bash_tool,
    is_edit_like_tool,
)
from .._helpers import (
    decision_for_context,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._source_parse import _line_count as _line_count, _normalized_module_path as _normalized_module_path, _python_ast_rule_is_disabled as _python_ast_rule_is_disabled, _resolve_python_path as _resolve_python_path


def _module_split_scenario(path_value: str) -> str:
    """Classify an oversized module so hook guidance can be specific."""
    normalized = _normalized_module_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    name_scenarios = {"conftest.py": "conftest", "__init__.py": "package-init"}
    if scenario := name_scenarios.get(name):
        return scenario
    if name.startswith("test_") or normalized.startswith("tests/") or "/tests/" in normalized:
        return "test-module"
    entrypoint_names = {"cli.py", "main.py", "app.py"}
    if name in entrypoint_names or normalized.endswith("/routes.py"):
        return "entrypoint-or-router"
    return "module-to-package"


_OVERSIZED_SPLIT_PLANS = {
    "conftest": (
        "conftest.py is a fixture registry, not a dumping ground. Keep pytest "
        "fixtures and local plugin hooks there; move event factories, fake clients, "
        "fake apps, builders, pilot/wait helpers, and assertion helpers into "
        "`tests/<area>/support/` modules. If fixtures only serve one subtree, move "
        "them into that subtree's narrower conftest.py. Import helpers into conftest "
        "and expose only the fixtures pytest must discover."
    ),
    "package-init": (
        "A large __init__.py should become a facade only: move implementation into "
        "sibling modules/subpackages, keep __all__ and compatibility re-exports, and "
        "avoid side effects at import time."
    ),
    "test-module": (
        "For an oversized test module, split by behavior under test, not by random "
        "ranges. Move reusable factories/fakes/assertion helpers into test support "
        "modules; use pytest parametrization for repeated scenarios; keep each test "
        "file focused on one surface or workflow."
    ),
    "entrypoint-or-router": (
        "For a bloated CLI/app/router module, split parsing/routing from behavior: "
        "commands/routes stay thin, orchestration moves to services, schemas/models "
        "move to dedicated modules, and side-effect adapters live at the edge."
    ),
    "module-to-package": (
        "Convert the module into a package when one file owns multiple concerns: "
        "`module.py` -> `module/` with `__init__.py` re-exporting the old public API, "
        "then split into focused modules such as models/types, parsing, persistence, "
        "services/orchestration, adapters/IO, constants/data, and errors. If the file "
        "is mostly generated data or giant literals, move that data into fixtures, "
        "resources, or builders instead of hiding it in Python code."
    ),
}


def _oversized_module_split_guidance(path_value: str, scenario: str) -> str:
    """Return scenario-aware recovery guidance for an oversized Python module."""
    verification = (
        f"Verify after the split: `python3 -m py_compile {path_value}` plus the "
        "smallest focused test/lint command that covers the moved code."
    )
    common = (
        "Oversized module split playbook:\n"
        "1) Do not cut by line number alone; split around responsibilities and import seams.\n"
        "2) Preserve public imports with a small facade/re-export layer when callers exist.\n"
        "3) Move tests with the behavior, then run the narrowest compile/test check.\n"
        "Line-count camouflage is not a fix: do not delete blank lines, compress "
        "formatting, or shuffle comments just to duck the threshold; ruff/formatters "
        "will normalize style while the oversized-module design smell remains."
    )
    plan = _OVERSIZED_SPLIT_PLANS.get(scenario, _OVERSIZED_SPLIT_PLANS["module-to-package"])
    return f"{plan}\n\n{common}\n{verification}"


def _significant_line_fingerprint(source: str) -> tuple[str, ...]:
    """Return content lines after removing blank-line padding only."""
    return tuple(line.rstrip() for line in source.splitlines() if line.strip())


def _is_line_count_camouflage(before: str, after: str) -> bool:
    """Detect blank-line/spacing shaving on an already-oversized module."""
    before_lines = _line_count(before)
    after_lines = _line_count(after)
    return (
        before_lines > LINT_MAX_MODULE_LINES_SOFT
        and after_lines < before_lines
        and _significant_line_fingerprint(before) == _significant_line_fingerprint(after)
    )


def _read_python_source(ctx: HookContext, path_value: str) -> str | None:
    """Read a Python path relative to the hook cwd; return None on failure."""
    try:
        return _resolve_python_path(ctx, path_value).read_text(encoding="utf-8")
    except OSError:
        return None


def _project_replacement(
    ctx: HookContext,
    path_value: str,
    old_string: str,
    new_string: str,
) -> str | None:
    """Return projected file content after a single replacement edit."""
    if not old_string:
        return None
    source = _read_python_source(ctx, path_value)
    if source is None or old_string not in source:
        return None
    return source.replace(old_string, new_string, 1)


def _project_top_level_edit(ctx: HookContext, tool_input: ObjectDict) -> tuple[str, str] | None:
    """Project a Claude/OpenCode-style single Edit payload into final source."""
    path_value = extract_path_from_mapping(tool_input)
    if (
        not path_value
        or not path_value.lower().endswith((".py", ".pyi"))
        or is_third_party_or_virtualenv_path(path_value)
    ):
        return None
    old_string = first_present(
        tool_input,
        ("old_string", "oldString", "old_text", "oldText"),
        strip=False,
    )
    new_string = first_present(
        tool_input,
        ("new_string", "newString", "new_text", "newText"),
        strip=False,
    )
    projected = _project_replacement(ctx, path_value, old_string, new_string)
    if projected is None:
        return None
    return path_value, projected


def _project_multiedit_sources(ctx: HookContext, tool_input: ObjectDict) -> list[tuple[str, str]]:
    """Project MultiEdit payloads into final per-file source content."""
    default_path = extract_path_from_mapping(tool_input)
    projected_by_path: dict[str, str] = {}
    for item in object_list(tool_input.get("edits")):
        item_dict = object_dict(item)
        path_value = extract_path_from_mapping(item_dict) or default_path
        if (
            not path_value
            or not path_value.lower().endswith((".py", ".pyi"))
            or is_third_party_or_virtualenv_path(path_value)
        ):
            continue
        source = projected_by_path.get(path_value)
        if source is None:
            source = _read_python_source(ctx, path_value)
        if source is None:
            continue
        old_string = first_present(
            item_dict,
            ("old_string", "oldString", "old_text", "oldText"),
            strip=False,
        )
        new_string = first_present(
            item_dict,
            ("new_string", "newString", "new_text", "newText"),
            strip=False,
        )
        if old_string and old_string in source:
            projected_by_path[path_value] = source.replace(old_string, new_string, 1)
    return [(path_value, source) for path_value, source in projected_by_path.items()]


def _is_authored_python_path(path_value: str) -> bool:
    return path_value.lower().endswith((".py", ".pyi")) and not is_third_party_or_virtualenv_path(path_value)


def _dedupe_sources(sources: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(sources))


def _pre_python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    top_level_projection = _project_top_level_edit(ctx, ctx.tool_input)
    if top_level_projection is not None:
        sources.append(top_level_projection)
    sources.extend(_project_multiedit_sources(ctx, ctx.tool_input))
    for ct in ctx.content_targets:
        if _is_authored_python_path(ct.path) and ct.source not in {"multi_edit", "multi_edit_old"}:
            sources.append((ct.path, ct.content))
    return sources


def _post_python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    if not (is_edit_like_tool(ctx.tool_name) or is_bash_tool(ctx.tool_name)):
        return []
    sources: list[tuple[str, str]] = []
    for path_value in ctx.candidate_paths:
        if not _is_authored_python_path(path_value):
            continue
        source = _read_python_source(ctx, path_value)
        if source is not None:
            sources.append((path_value, source))
    return sources


def _project_top_level_before_after(
    ctx: HookContext,
    tool_input: ObjectDict,
) -> tuple[str, str, str] | None:
    path_value = extract_path_from_mapping(tool_input)
    if not path_value or not _is_authored_python_path(path_value):
        return None
    old_string = first_present(
        tool_input,
        ("old_string", "oldString", "old_text", "oldText"),
        strip=False,
    )
    new_string = first_present(
        tool_input,
        ("new_string", "newString", "new_text", "newText"),
        strip=False,
    )
    if not old_string:
        return None
    source = _read_python_source(ctx, path_value)
    if source is None or old_string not in source:
        return None
    return path_value, source, source.replace(old_string, new_string, 1)


def _pre_python_camouflage_sources(ctx: HookContext) -> list[tuple[str, str, str]]:
    if ctx.event_name not in (PRE_TOOL_USE, PERMISSION_REQUEST):
        return []
    sources: list[tuple[str, str, str]] = []
    top_level_projection = _project_top_level_before_after(ctx, ctx.tool_input)
    if top_level_projection is not None:
        sources.append(top_level_projection)
    for path_value, projected in _project_multiedit_sources(ctx, ctx.tool_input):
        before = _read_python_source(ctx, path_value)
        if before is not None:
            sources.append((path_value, before, projected))
    for ct in ctx.content_targets:
        if not _is_authored_python_path(ct.path) or ct.source in {"multi_edit", "multi_edit_old"}:
            continue
        before = _read_python_source(ctx, ct.path)
        if before is not None:
            sources.append((ct.path, before, ct.content))
    return _dedupe_camouflage_sources(sources)


def _dedupe_camouflage_sources(sources: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    deduped: dict[tuple[str, str], tuple[str, str, str]] = {}
    for path_value, before, after in sources:
        deduped.setdefault((path_value, after), (path_value, before, after))
    return list(deduped.values())


def _python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    """Return full/projection Python sources for size-oriented hook checks.

    Unlike general AST rules, size checks must understand both complete-file
    writes and edit payloads whose final file crosses a threshold.
    """
    if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST):
        return _dedupe_sources(_pre_python_structural_sources(ctx))
    return _dedupe_sources(_post_python_structural_sources(ctx))


class _LineCountCamouflageFinding(NamedTuple):
    path_value: str
    before_lines: int
    after_lines: int


class _ModuleSizeFinding(NamedTuple):
    path_value: str
    line_count: int
    hard: bool


@final
class PythonModuleSizeRule(Rule):
    """Block Python modules that exceed lint module line-count thresholds."""

    rule_id = "PY-CODE-018"
    title = "Block oversized Python module"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST)

    def _finding(self, ctx: HookContext, finding: _ModuleSizeFinding) -> RuleFinding:
        threshold = LINT_MAX_MODULE_LINES_HARD if finding.hard else LINT_MAX_MODULE_LINES_SOFT
        collector = "oversized-module" if finding.hard else "oversized-module-soft"
        severity = Severity.HIGH if finding.hard else Severity.MEDIUM
        scenario = _module_split_scenario(finding.path_value)
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=severity,
            decision=decision_for_context(ctx),
            message=(
                f"Python module `{finding.path_value}` is {collector}: "
                f"{finding.line_count} lines exceeds limit {threshold}. "
                f"Use the {scenario} split plan before writing it; line-count "
                "camouflage will be blocked."
            ),
            additional_context=_oversized_module_split_guidance(finding.path_value, scenario),
            metadata={
                METADATA_PATH: finding.path_value,
                "collector": collector,
                "split_scenario": scenario,
                "lines": finding.line_count,
                "limit": threshold,
            },
        )

    def _camouflage_finding(
        self,
        ctx: HookContext,
        finding: _LineCountCamouflageFinding,
    ) -> RuleFinding:
        scenario = _module_split_scenario(finding.path_value)
        removed = finding.before_lines - finding.after_lines
        return RuleFinding(
            rule_id=self.rule_id,
            title="Block oversized-module line-count camouflage",
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Line-count camouflage on oversized module `{finding.path_value}`: "
                f"the edit removes {removed} blank/spacing lines "
                f"({finding.before_lines} -> {finding.after_lines}) while keeping the "
                "same nonblank content. Do a package/facade split instead of shaving "
                "empty space."
            ),
            additional_context=_oversized_module_split_guidance(finding.path_value, scenario),
            metadata={
                METADATA_PATH: finding.path_value,
                "collector": "line-count-camouflage",
                "split_scenario": scenario,
                "before_lines": finding.before_lines,
                "after_lines": finding.after_lines,
                "removed_lines": removed,
            },
        )

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if _python_ast_rule_is_disabled(ctx, self.rule_id):
            return []
        findings: list[RuleFinding] = []
        camouflage_paths: set[str] = set()
        for path_value, before, after in _pre_python_camouflage_sources(ctx):
            if not _is_line_count_camouflage(before, after):
                continue
            camouflage_paths.add(path_value)
            findings.append(
                self._camouflage_finding(
                    ctx,
                    _LineCountCamouflageFinding(
                        path_value,
                        _line_count(before),
                        _line_count(after),
                    ),
                )
            )
        for path_value, source in _python_structural_sources(ctx):
            if path_value in camouflage_paths:
                continue
            line_count = _line_count(source)
            if line_count > LINT_MAX_MODULE_LINES_HARD:
                findings.append(
                    self._finding(
                        ctx,
                        _ModuleSizeFinding(path_value, line_count, hard=True),
                    )
                )
            elif line_count > LINT_MAX_MODULE_LINES_SOFT:
                findings.append(
                    self._finding(
                        ctx,
                        _ModuleSizeFinding(path_value, line_count, hard=False),
                    )
                )
        return findings
