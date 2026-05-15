from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, final
from typing_extensions import override

from vibeforcer._types import ObjectDict, object_dict, object_list
from vibeforcer.constants import (
    LINT_MAX_MODULE_LINES_HARD,
    LINT_MAX_MODULE_LINES_SOFT,
    MAX_GOD_CLASS_LINES,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.util.payloads import (
    extract_path_from_mapping,
    first_present,
    is_bash_tool,
    is_edit_like_tool,
)

from ._helpers import (
    decision_for_context,
    detect_family_prefix,
    evaluate_common,
    parse_module,
)

if TYPE_CHECKING:
    from vibeforcer.context import HookContext


def _parse_strict(source: str, max_chars: int) -> ast.Module | None:
    """Parse source into a module; return None when too large or syntactically invalid."""
    if len(source) > max_chars:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _first_significant_line(source: str) -> str:
    """Return the first non-empty, non-comment line from source."""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return line
    return ""


def _looks_like_indented_fragment(source: str, exc: SyntaxError) -> bool:
    """Return True when a parse error is probably an edit fragment, not a module."""
    if exc.msg != "unexpected indent":
        return False
    first_line = _first_significant_line(source)
    return bool(first_line and first_line[:1].isspace())


def _parse_health_failure(
    source: str,
    max_chars: int,
    *,
    suppress_fragments: bool,
) -> str | None:
    """Return the health failure kind, or None when source is parseable/fragmental."""
    if len(source) > max_chars:
        return "oversized"
    try:
        ast.parse(source)
    except RecursionError:
        return "parse_error"
    except SyntaxError as exc:
        if suppress_fragments and _looks_like_indented_fragment(source, exc):
            return None
        return "parse_error"
    return None


def _is_full_module_candidate(ctx: HookContext, source_kind: str) -> bool:
    """Return True when pre-edit content likely represents a full Python module.

    `Edit`, `MultiEdit`, and patch-style payloads frequently contain fragments rather
    than a complete file. Those fragments are still useful for targeted AST rules, but
    they should not trip the fail-closed AST health rule.
    """
    tool_name = ctx.tool_name.lower()
    if source_kind in {"multi_edit", "multi_edit_old", "patch"}:
        return False
    if tool_name != "write" and is_edit_like_tool(ctx.tool_name):
        return False
    if tool_name in {
        "edit",
        "multiedit",
        "multi_edit",
        "patch",
        "applypatch",
        "apply_patch",
    }:
        return False
    return True


def _resolve_python_path(ctx: HookContext, path_value: str) -> Path:
    """Resolve Python file paths consistently for AST-based rules."""
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return raw_path
    return (ctx.cwd / raw_path).resolve()


def _line_count(source: str) -> int:
    """Return the line count in the same spirit as lint read_lines()."""
    return len(source.splitlines())


def _normalized_module_path(path_value: str) -> str:
    """Return a slash-normalized path for scenario checks."""
    return path_value.replace("\\", "/").lower()



def _module_split_scenario(path_value: str) -> str:
    """Classify an oversized module so hook guidance can be specific."""
    normalized = _normalized_module_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    if name == "conftest.py":
        return "conftest"
    if name == "__init__.py":
        return "package-init"
    if name.startswith("test_") or normalized.startswith("tests/") or "/tests/" in normalized:
        return "test-module"
    if name in {"cli.py", "main.py", "app.py"} or normalized.endswith("/routes.py"):
        return "entrypoint-or-router"
    return "module-to-package"


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
        "3) Move tests with the behavior, then run the narrowest compile/test check."
    )
    if scenario == "conftest":
        return (
            "conftest.py is a fixture registry, not a dumping ground. Keep pytest "
            "fixtures and local plugin hooks there; move event factories, fake clients, "
            "fake apps, builders, pilot/wait helpers, and assertion helpers into "
            "`tests/<area>/support/` modules. If fixtures only serve one subtree, move "
            "them into that subtree's narrower conftest.py. Import helpers into conftest "
            "and expose only the fixtures pytest must discover.\n\n"
            f"{common}\n{verification}"
        )
    if scenario == "package-init":
        return (
            "A large __init__.py should become a facade only: move implementation into "
            "sibling modules/subpackages, keep __all__ and compatibility re-exports, and "
            "avoid side effects at import time.\n\n"
            f"{common}\n{verification}"
        )
    if scenario == "test-module":
        return (
            "For an oversized test module, split by behavior under test, not by random "
            "ranges. Move reusable factories/fakes/assertion helpers into test support "
            "modules; use pytest parametrization for repeated scenarios; keep each test "
            "file focused on one surface or workflow.\n\n"
            f"{common}\n{verification}"
        )
    if scenario == "entrypoint-or-router":
        return (
            "For a bloated CLI/app/router module, split parsing/routing from behavior: "
            "commands/routes stay thin, orchestration moves to services, schemas/models "
            "move to dedicated modules, and side-effect adapters live at the edge.\n\n"
            f"{common}\n{verification}"
        )
    return (
        "Convert the module into a package when one file owns multiple concerns: "
        "`module.py` -> `module/` with `__init__.py` re-exporting the old public API, "
        "then split into focused modules such as models/types, parsing, persistence, "
        "services/orchestration, adapters/IO, constants/data, and errors. If the file "
        "is mostly generated data or giant literals, move that data into fixtures, "
        "resources, or builders instead of hiding it in Python code.\n\n"
        f"{common}\n{verification}"
    )


def _class_body_lines(node: ast.ClassDef) -> int:
    """Count the total lines spanned by a class body."""
    if not node.body:
        return 0
    first = node.body[0]
    last = node.body[-1]
    start = first.lineno
    end = getattr(last, "end_lineno", last.lineno)
    return end - start + 1


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
    if not path_value or not path_value.lower().endswith((".py", ".pyi")):
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
        if not path_value or not path_value.lower().endswith((".py", ".pyi")):
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


def _python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    """Return full/projection Python sources for size-oriented hook checks.

    Unlike general AST rules, size checks must understand both complete-file
    writes and edit payloads whose final file crosses a threshold.
    """
    sources: list[tuple[str, str]] = []
    is_pre = ctx.event_name in ("PreToolUse", "PermissionRequest")
    if is_pre:
        tool_input = ctx.tool_input
        top_level_projection = _project_top_level_edit(ctx, tool_input)
        if top_level_projection is not None:
            sources.append(top_level_projection)
        sources.extend(_project_multiedit_sources(ctx, tool_input))
        for ct in ctx.content_targets:
            if not ct.path.lower().endswith((".py", ".pyi")):
                continue
            if ct.source in {"multi_edit", "multi_edit_old"}:
                continue
            sources.append((ct.path, ct.content))
    else:
        if not (is_edit_like_tool(ctx.tool_name) or is_bash_tool(ctx.tool_name)):
            return []
        for path_value in ctx.candidate_paths:
            if not path_value.lower().endswith((".py", ".pyi")):
                continue
            source = _read_python_source(ctx, path_value)
            if source is not None:
                sources.append((path_value, source))

    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path_value, source in sources:
        key = (path_value, source)
        if key in seen:
            continue
        seen.add(key)
        unique.append((path_value, source))
    return unique


@final
class PythonModuleSizeRule(Rule):
    """Block Python modules that exceed lint module line-count thresholds."""

    rule_id = "PY-CODE-018"
    title = "Block oversized Python module"
    events = ("PreToolUse", "PermissionRequest")

    def _finding(
        self,
        ctx: HookContext,
        path_value: str,
        line_count: int,
        *,
        hard: bool,
    ) -> RuleFinding:
        threshold = LINT_MAX_MODULE_LINES_HARD if hard else LINT_MAX_MODULE_LINES_SOFT
        collector = "oversized-module" if hard else "oversized-module-soft"
        severity = Severity.HIGH if hard else Severity.MEDIUM
        scenario = _module_split_scenario(path_value)
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=severity,
            decision=decision_for_context(ctx),
            message=(
                f"Python module `{path_value}` is {collector}: {line_count} lines "
                f"exceeds limit {threshold}. Use the {scenario} split plan before writing it."
            ),
            additional_context=_oversized_module_split_guidance(path_value, scenario),
            metadata={
                "path": path_value,
                "collector": collector,
                "split_scenario": scenario,
                "lines": line_count,
                "limit": threshold,
            },
        )

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.config.python_ast_enabled:
            return []
        findings: list[RuleFinding] = []
        for path_value, source in _python_structural_sources(ctx):
            line_count = _line_count(source)
            if line_count > LINT_MAX_MODULE_LINES_HARD:
                findings.append(self._finding(ctx, path_value, line_count, hard=True))
            elif line_count > LINT_MAX_MODULE_LINES_SOFT:
                findings.append(self._finding(ctx, path_value, line_count, hard=False))
        return findings


@final
class PythonAstHealthRule(Rule):
    """Emit findings when AST checks cannot run due to parse/read failures."""

    rule_id = "PY-AST-001"
    title = "Python AST parse/read failure"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def _finding(self, ctx: HookContext, path_value: str, kind: str) -> RuleFinding:
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=f"Python AST analysis could not run for `{path_value}` ({kind}).",
            additional_context=(
                "Stop broad refactors until this file parses. "
                f"Reread `{path_value}` in full, run `python3 -m py_compile {path_value}`, "
                "then repair syntax/readability before continuing."
            ),
            metadata={"path": path_value, "kind": kind},
        )

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.config.python_ast_enabled:
            return []
        findings: list[RuleFinding] = []
        is_pre = ctx.event_name in ("PreToolUse", "PermissionRequest")
        if is_pre:
            for ct in ctx.content_targets:
                if not ct.path.lower().endswith((".py", ".pyi")):
                    continue
                if not _is_full_module_candidate(ctx, ct.source):
                    continue
                failure = _parse_health_failure(
                    ct.content,
                    ctx.config.python_ast_max_parse_chars,
                    suppress_fragments=True,
                )
                if failure == "oversized" and _line_count(ct.content) > LINT_MAX_MODULE_LINES_SOFT:
                    continue
                if failure is not None:
                    findings.append(self._finding(ctx, ct.path, failure))
        else:
            if not (is_edit_like_tool(ctx.tool_name) or is_bash_tool(ctx.tool_name)):
                return []
            for path_value in ctx.candidate_paths:
                if not path_value.lower().endswith((".py", ".pyi")):
                    continue
                full_path = _resolve_python_path(ctx, path_value)
                try:
                    source = full_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    if ctx.event_name == "PostToolUse" and is_bash_tool(ctx.tool_name):
                        continue
                    findings.append(self._finding(ctx, path_value, "read_error"))
                    continue
                except OSError:
                    findings.append(self._finding(ctx, path_value, "read_error"))
                    continue
                failure = _parse_health_failure(
                    source,
                    ctx.config.python_ast_max_parse_chars,
                    suppress_fragments=False,
                )
                if failure == "oversized" and _line_count(source) > LINT_MAX_MODULE_LINES_SOFT:
                    continue
                if failure is not None:
                    findings.append(self._finding(ctx, path_value, failure))
        return findings


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    exc_type = handler.type
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Name):
        return exc_type.id in {"Exception", "BaseException"}
    if isinstance(exc_type, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id in {"Exception", "BaseException"}
            for item in exc_type.elts
        )
    return False


def _is_logger_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return func.value.id in {"logger", "logging"}
        return func.attr in {"error", "warning", "warn", "exception", "info"}
    return False


def _is_empty_default_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False, ""}
    if isinstance(value, ast.List):
        return len(value.elts) == 0
    if isinstance(value, ast.Dict):
        return len(value.keys) == 0
    return False


@final
class PythonBroadExceptLoggerRule(Rule):
    rule_id = "PY-EXC-001"
    title = "Block broad exception handler"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        for node in ast.walk(module):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not _is_broad_exception(handler):
                    continue
                has_logger = any(_is_logger_call(inner) for stmt in handler.body for inner in ast.walk(stmt))
                has_raise = any(isinstance(inner, ast.Raise) for stmt in handler.body for inner in ast.walk(stmt))
                if has_logger and not has_raise:
                    return [
                        RuleFinding(
                            rule_id=self.rule_id,
                            title=self.title,
                            severity=Severity.HIGH,
                            decision=decision_for_context(ctx),
                            message=(
                                f"Broad exception handler in `{path_value}` logs without re-raising. "
                                "Catch specific exceptions or propagate with context."
                            ),
                            metadata={"path": path_value},
                        )
                    ]
        return []

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonSilentExceptRule(Rule):
    rule_id = "PY-EXC-002"
    title = "Block silent exception swallow"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        for node in ast.walk(module):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not _is_broad_exception(handler):
                    continue
                for stmt in handler.body:
                    if isinstance(stmt, (ast.Pass, ast.Continue)):
                        return [
                            RuleFinding(
                                rule_id=self.rule_id,
                                title=self.title,
                                severity=Severity.HIGH,
                                decision=decision_for_context(ctx),
                                message=f"Silent broad exception swallow in `{path_value}`.",
                                metadata={"path": path_value},
                            )
                        ]
                    if isinstance(stmt, ast.Return) and _is_empty_default_return(stmt):
                        return [
                            RuleFinding(
                                rule_id=self.rule_id,
                                title=self.title,
                                severity=Severity.HIGH,
                                decision=decision_for_context(ctx),
                                message=(
                                    f"Broad exception handler in `{path_value}` returns an empty default."
                                ),
                                metadata={"path": path_value},
                            )
                        ]
        return []

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonLongMethodRule(Rule):
    rule_id = "PY-CODE-008"
    title = "Block long Python methods"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _worst_function(module: ast.Module, limit: int) -> tuple[str, int] | None:
        """Return (name, span) of the longest over-limit function, or None."""
        worst: tuple[str, int] | None = None
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue
            span = node.end_lineno - node.lineno + 1
            if span > limit and (worst is None or span > worst[1]):
                worst = (node.name, span)
        return worst

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        """Return findings for any too-long functions in source."""
        module = _parse_strict(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst = self._worst_function(module, ctx.config.python_long_method_lines)
        if worst is None:
            return []
        name, span = worst
        limit = ctx.config.python_long_method_lines
        decision = (
            "deny" if ctx.event_name in ("PreToolUse", "PermissionRequest") else "block"
        )
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision,
            message=(
                f"Python function `{name}` in `{path_value}` is {span} lines long. "
                f"Keep functions under {limit} lines or split them into helpers."
            ),
            metadata={"path": path_value, "function": name, "lines": span},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonLongParameterRule(Rule):
    rule_id = "PY-CODE-009"
    title = "Block long Python parameter lists"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _worst_param_count(module: ast.Module, limit: int) -> tuple[str, int] | None:
        """Return (name, count) of the function with the most over-limit params."""
        worst: tuple[str, int] | None = None
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
            names = [arg.arg for arg in args]
            if names and names[0] in {"self", "cls"}:
                names = names[1:]
            if len(names) > limit and (worst is None or len(names) > worst[1]):
                worst = (node.name, len(names))
        return worst

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        """Return findings for any too-long parameter lists in source."""
        module = _parse_strict(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst = self._worst_param_count(module, ctx.config.python_long_parameter_limit)
        if worst is None:
            return []
        name, count = worst
        limit = ctx.config.python_long_parameter_limit
        decision = (
            "deny" if ctx.event_name in ("PreToolUse", "PermissionRequest") else "block"
        )
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.MEDIUM,
            decision=decision,
            message=(
                f"Python function `{name}` in `{path_value}` declares {count} parameters. "
                f"Keep functions at or below {limit} parameters or group inputs into objects."
            ),
            metadata={"path": path_value, "function": name, "parameter_count": count},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# New rules (PY-CODE-010 through PY-CODE-016)
# ---------------------------------------------------------------------------


@final
class PythonLongLineRule(Rule):
    """PY-CODE-010: Block files containing lines over 120 characters."""

    rule_id = "PY-CODE-010"
    title = "Block long lines"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _toggle_docstring(stripped: str, in_docstring: bool) -> bool:
        """Return updated docstring-tracking state after processing stripped."""
        for marker in ('"""', "'''"):
            if stripped.count(marker) % 2 == 1:
                in_docstring = not in_docstring
        return in_docstring

    def _find_worst_line(self, source: str, max_length: int) -> tuple[int, int]:
        """Scan source and return (lineno, length) of the longest offending line."""
        in_docstring = False
        worst_lineno = 0
        worst_length = 0
        for lineno, raw_line in enumerate(source.splitlines(), start=1):
            stripped = raw_line.strip()
            in_docstring = self._toggle_docstring(stripped, in_docstring)
            if in_docstring or stripped.startswith("#"):
                continue
            if "http://" in raw_line or "https://" in raw_line:
                continue
            if len(raw_line) > max_length and len(raw_line) > worst_length:
                worst_lineno = lineno
                worst_length = len(raw_line)
        return worst_lineno, worst_length

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        max_length = ctx.config.python_max_line_length
        if len(source) > ctx.config.python_ast_max_parse_chars:
            return []
        worst_lineno, worst_length = self._find_worst_line(source, max_length)
        if worst_length <= max_length:
            return []
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.MEDIUM,
            decision=decision_for_context(ctx),
            message=(
                f"Line {worst_lineno} in `{path_value}` is {worst_length} characters long. "
                f"Keep lines at or below {max_length} characters."
            ),
            metadata={"path": path_value, "line": worst_lineno, "length": worst_length},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonDeepNestingRule(Rule):
    """PY-CODE-011: Block functions with nesting depth > 4."""

    rule_id = "PY-CODE-011"
    title = "Block deep nesting"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    _NESTING_TYPES = (
        ast.If,
        ast.For,
        ast.While,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.ExceptHandler,
    )

    def _max_nesting(self, node: ast.AST, depth: int = 0) -> int:
        """Return the maximum nesting depth below node."""
        max_d = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, self._NESTING_TYPES):
                max_d = max(max_d, self._max_nesting(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting(child, depth))
        return max_d

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst_name = ""
        worst_depth = 0
        for node in ast.walk(module):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                depth = self._max_nesting(node, 0)
                if depth > ctx.config.python_max_nesting_depth and depth > worst_depth:
                    worst_name = node.name
                    worst_depth = depth
        if not worst_name:
            return []
        limit = ctx.config.python_max_nesting_depth
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Function `{worst_name}` in `{path_value}` has nesting depth {worst_depth}. "
                f"Keep nesting at or below {limit} levels."
            ),
            metadata={"path": path_value, "function": worst_name, "depth": worst_depth},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonFeatureEnvyRule(Rule):
    """PY-CODE-012: Detect functions where >60% of attribute accesses target one external object."""

    rule_id = "PY-CODE-012"
    title = "Block feature envy"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    _IGNORE_NAMES = frozenset({
        "os", "sys", "re", "io", "abc", "ast", "csv", "json", "math", "time",
        "uuid", "enum", "copy", "gzip", "html", "http", "shutil", "signal",
        "socket", "string", "struct", "typing", "base64", "codecs", "hashlib",
        "logging", "pathlib", "secrets", "sqlite3", "urllib", "asyncio",
        "collections", "contextlib", "dataclasses", "datetime", "functools",
        "importlib", "itertools", "multiprocessing", "operator", "platform",
        "pprint", "random", "subprocess", "tempfile", "textwrap", "threading",
        "traceback", "unittest", "warnings", "np", "pd", "plt", "tf", "torch",
        "sk", "Path", "Enum", "Optional", "Union", "List", "Dict", "Set", "Tuple",
    })

    @staticmethod
    def _root_name(node: ast.Attribute) -> str | None:
        """Walk down the Attribute chain to find the root Name."""
        current: ast.AST = node.value
        while isinstance(current, ast.Attribute):
            current = current.value
        if isinstance(current, ast.Name):
            return current.id
        return None

    @staticmethod
    def _param_names(
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> frozenset[str]:
        """Collect all parameter names from a function signature."""
        names: list[str] = []
        for arg in (
            func_node.args.args + func_node.args.posonlyargs + func_node.args.kwonlyargs
        ):
            names.append(arg.arg)
        if func_node.args.vararg:
            names.append(func_node.args.vararg.arg)
        if func_node.args.kwarg:
            names.append(func_node.args.kwarg.arg)
        return frozenset(names)

    def _count_envy_accesses(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        param_ns: frozenset[str],
    ) -> tuple[dict[str, int], int]:
        """Count attribute accesses per external object in node."""
        counts: dict[str, int] = {}
        total = 0
        for child in ast.walk(node):
            if not isinstance(child, ast.Attribute):
                continue
            root = self._root_name(child)
            if root is None or root in ("self", "cls") or root in self._IGNORE_NAMES:
                continue
            if root in param_ns:
                continue
            counts[root] = counts.get(root, 0) + 1
            total += 1
        return counts, total

    def _check_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        path_value: str,
        ctx: HookContext,
    ) -> RuleFinding | None:
        """Return a finding if node exhibits feature envy, else None."""
        param_ns = self._param_names(node)
        counts, total = self._count_envy_accesses(node, param_ns)
        if total < ctx.config.python_feature_envy_min_accesses:
            return None
        for obj_name, count in counts.items():
            if count / total > ctx.config.python_feature_envy_threshold:
                return RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.LOW,
                    decision="context",
                    message=(
                        f"Function `{node.name}` in `{path_value}` has feature envy: "
                        f"{count}/{total} attribute accesses target `{obj_name}`. "
                        "Advisory only: this is context for a future design pass; "
                        "do not retry the write solely for this. Consider moving "
                        f"this logic to {obj_name}'s class when you are already "
                        "touching that boundary."
                    ),
                    metadata={
                        "path": path_value,
                        "function": node.name,
                        "envied_object": obj_name,
                        "accesses": count,
                        "total": total,
                    },
                )
        return None

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            finding = self._check_function(node, path_value, ctx)
            if finding is not None:
                findings.append(finding)
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonThinWrapperRule(Rule):
    """PY-CODE-013: Detect functions whose body is a single delegating call."""

    rule_id = "PY-CODE-013"
    title = "Block thin wrappers"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _extract_single_call(stmt: ast.stmt) -> ast.Call | None:
        """Return the Call node if stmt is a single-statement Return/Expr call."""
        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
            return stmt.value
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            return stmt.value
        return None

    @staticmethod
    def _call_target_name(call_node: ast.Call) -> str:
        func = call_node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return PythonThinWrapperRule._attribute_name(func)
        return "<unknown>"

    @staticmethod
    def _attribute_name(node: ast.Attribute) -> str:
        parts: list[str] = [node.attr]
        current: ast.expr = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        else:
            return node.attr
        return ".".join(reversed(parts))

    @staticmethod
    def _call_root_name(call_node: ast.Call) -> str | None:
        func = call_node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            current: ast.expr = func
            while isinstance(current, ast.Attribute):
                current = current.value
            if isinstance(current, ast.Name):
                return current.id
        return None

    @staticmethod
    def _has_self_or_cls_receiver(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        call_node: ast.Call,
    ) -> bool:
        if not node.args.args:
            return False
        receiver_name = node.args.args[0].arg
        if receiver_name not in {"self", "cls"}:
            return False
        return PythonThinWrapperRule._call_root_name(call_node) == receiver_name

    @staticmethod
    def _is_test_helper_path(path_value: str) -> bool:
        normalized = path_value.replace("\\", "/").lower()
        return (
            normalized.startswith("tests/")
            or "/tests/" in normalized
            or normalized.endswith("/conftest.py")
            or normalized == "conftest.py"
        )

    @staticmethod
    def _is_exempt_cast_wrapper(call_node: ast.Call) -> bool:
        return isinstance(call_node.func, ast.Name) and call_node.func.id == "cast"

    @staticmethod
    def _is_exempt_test_helper_wrapper(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        call_node: ast.Call,
        path_value: str,
    ) -> bool:
        if not PythonThinWrapperRule._is_test_helper_path(path_value):
            return False
        if isinstance(call_node.func, ast.Name) and call_node.func.id in {"list", "cast"}:
            return True
        return PythonThinWrapperRule._has_self_or_cls_receiver(node, call_node)

    @staticmethod
    def _is_wrapper_candidate(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """Return True when node is a non-dunder, undecorated single-statement function."""
        if node.name.startswith("__") and node.name.endswith("__"):
            return False
        if node.decorator_list:
            return False
        return len(node.body) == 1

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not self._is_wrapper_candidate(node):
                continue
            call_node = self._extract_single_call(node.body[0])
            if call_node is None:
                continue
            if self._is_exempt_cast_wrapper(call_node):
                continue
            if self._is_exempt_test_helper_wrapper(node, call_node, path_value):
                continue
            wrapped = self._call_target_name(call_node)
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.MEDIUM,
                decision=decision_for_context(ctx),
                message=(
                    f"Function `{node.name}` in `{path_value}` is a thin wrapper "
                    f"around `{wrapped}`. Consider calling the wrapped function directly."
                ),
                metadata={"path": path_value, "function": node.name, "wraps": wrapped},
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonGodClassRule(Rule):
    """PY-CODE-014: Block god classes by method count or class body size."""

    rule_id = "PY-CODE-014"
    title = "Block god class"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _non_dunder_method_count(node: ast.ClassDef) -> int:
        """Return count of non-dunder methods in a class body."""
        count = 0
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not (child.name.startswith("__") and child.name.endswith("__")):
                    count += 1
        return count

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        method_limit = ctx.config.python_max_god_class_methods
        line_limit = MAX_GOD_CLASS_LINES
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue
            method_count = self._non_dunder_method_count(node)
            body_lines = _class_body_lines(node)
            reasons: list[str] = []
            if method_count > method_limit:
                reasons.append(f"methods={method_count} (limit={method_limit})")
            if body_lines > line_limit:
                reasons.append(f"lines={body_lines} (limit={line_limit})")
            if not reasons:
                continue
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision_for_context(ctx),
                message=(
                    f"Class `{node.name}` in `{path_value}` is a god-class: "
                    f"{', '.join(reasons)}. Split responsibilities before writing it."
                ),
                metadata={
                    "path": path_value,
                    "class": node.name,
                    "collector": "god-class",
                    "method_count": method_count,
                    "method_limit": method_limit,
                    "body_lines": body_lines,
                    "line_limit": line_limit,
                },
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.config.python_ast_enabled:
            return []
        findings: list[RuleFinding] = []
        for path_value, source in _python_structural_sources(ctx):
            findings.extend(self._check_source(source, path_value, ctx))
        return findings



# Node types that each add 1 to cyclomatic complexity
_CC_BRANCH_TYPES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.comprehension,
)


@final
class PythonCyclomaticComplexityRule(Rule):
    """PY-CODE-015: Block functions with cyclomatic complexity > 10."""

    rule_id = "PY-CODE-015"
    title = "Block cyclomatic complexity"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _complexity(node: ast.AST) -> int:
        """Compute cyclomatic complexity for a function body."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, _CC_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst_name = ""
        worst_cc = 0
        for node in ast.walk(module):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = self._complexity(node)
                if cc > ctx.config.python_max_complexity and cc > worst_cc:
                    worst_name = node.name
                    worst_cc = cc
        if not worst_name:
            return []
        limit = ctx.config.python_max_complexity
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Function `{worst_name}` in `{path_value}` has cyclomatic complexity {worst_cc}. "
                f"Keep complexity at or below {limit}."
            ),
            metadata={"path": path_value, "function": worst_name, "complexity": worst_cc},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonDeadCodeRule(Rule):
    """PY-CODE-016: Detect unreachable code after return/raise/break/continue."""

    rule_id = "PY-CODE-016"
    title = "Block dead code after return"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    _TERMINAL = (ast.Return, ast.Raise, ast.Break, ast.Continue)

    def _scan_block(self, stmts: list[ast.stmt]) -> tuple[str | None, int]:
        """Return (description, lineno) of first dead statement, or (None, 0)."""
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, self._TERMINAL) and i < len(stmts) - 1:
                dead_stmt = stmts[i + 1]
                return (type(stmt).__name__.lower(), getattr(dead_stmt, "lineno", 0))
        return (None, 0)

    @staticmethod
    def _collect_blocks(child: ast.AST) -> list[list[ast.stmt]]:
        """Return all statement blocks owned by child that should be scanned."""
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [child.body]
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            blocks: list[list[ast.stmt]] = [child.body]
            if child.orelse:
                blocks.append(child.orelse)
            return blocks
        if isinstance(child, ast.Try):
            blocks = [child.body]
            for handler in child.handlers:
                blocks.append(handler.body)
            if child.orelse:
                blocks.append(child.orelse)
            if child.finalbody:
                blocks.append(child.finalbody)
            return blocks
        if isinstance(child, (ast.With, ast.AsyncWith, ast.ExceptHandler)):
            return [child.body]
        return []

    def _find_dead_code(self, node: ast.AST) -> list[tuple[str, int]]:
        """Walk all statement blocks and collect dead code locations."""
        results: list[tuple[str, int]] = []
        for child in ast.walk(node):
            for block in self._collect_blocks(child):
                cause, lineno = self._scan_block(block)
                if cause is not None:
                    results.append((cause, lineno))
        return results

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dead = self._find_dead_code(node)
            if not dead:
                continue
            cause, lineno = dead[0]
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision_for_context(ctx),
                message=(
                    f"Function `{node.name}` in `{path_value}` has unreachable code "
                    f"after `{cause}` at line {lineno}."
                ),
                metadata={
                    "path": path_value,
                    "function": node.name,
                    "dead_line": lineno,
                    "cause": cause,
                },
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# PY-CODE-017: Detect flat prefix_* sibling module sprawl
# ---------------------------------------------------------------------------


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
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

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
                "path": representative_path,
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
            full = _flat_sibling_resolve_candidate_path(ctx, path_value)
            parent = full.parent
            if parent.exists() and parent.is_dir():
                files = dirs.setdefault(parent, set())
                if ctx.event_name != "PostToolUse" or full.exists():
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
        if ctx.event_name in {"PreToolUse", "PermissionRequest"}:
            return is_edit_like_tool(ctx.tool_name)
        if ctx.event_name == "PostToolUse":
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
        decision = "deny" if ctx.event_name in {"PreToolUse", "PermissionRequest"} else "block"
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


# ---------------------------------------------------------------------------
# PY-IMPORT-002: Non-standard import aliases hide duplicate code
# ---------------------------------------------------------------------------

_ALLOWED_IMPORT_ALIASES: dict[str, str] = {
    "altair": "alt",
    "geopandas": "gpd",
    "jax.numpy": "jnp",
    "matplotlib": "mpl",
    "matplotlib.pyplot": "plt",
    "networkx": "nx",
    "numpy": "np",
    "pandas": "pd",
    "plotly.express": "px",
    "polars": "pl",
    "pyarrow": "pa",
    "pyspark.sql.functions": "F",
    "pyspark.sql.types": "T",
    "pyspark.sql.window": "W",
    "scipy": "sp",
    "seaborn": "sns",
    "sqlalchemy": "sa",
    "statsmodels.api": "sm",
    "statsmodels.formula.api": "smf",
    "sympy": "sp",
    "tensorflow": "tf",
    "tkinter": "tk",
    "tkinter.ttk": "ttk",
    "torch.nn": "nn",
    "xml.etree.ElementTree": "ET",
}


def _import_alias_full_name(node: ast.Import | ast.ImportFrom, name: ast.alias) -> str:
    """Return the imported object path used for alias allowlist checks."""
    if isinstance(node, ast.Import):
        return name.name
    module = node.module or ""
    if not module:
        return name.name
    return f"{module}.{name.name}"


def _allowed_import_alias(node: ast.Import | ast.ImportFrom, name: ast.alias) -> bool:
    """Return True when an import alias is a canonical library convention."""
    if name.asname is None:
        return True
    if name.name == "*":
        return False
    full_name = _import_alias_full_name(node, name)
    return _ALLOWED_IMPORT_ALIASES.get(full_name) == name.asname


def _import_alias_replacement(node: ast.Import | ast.ImportFrom, name: ast.alias) -> tuple[str, str]:
    """Return exact replacement import text and usage hint for a blocked alias."""
    if isinstance(node, ast.Import):
        return f"import {name.name}", f"{name.name}.<name>(...)"
    module = node.module or ""
    if module:
        return f"from {module} import {name.name}", f"{name.name}.<name>(...)"
    return f"import {name.name}", f"{name.name}.<name>(...)"


def _patch_added_source(source: str) -> str | None:
    """Extract added Python lines from a patch-like content target."""
    added: list[str] = []
    for line in source.splitlines():
        if line.startswith("+++") or line.startswith("***"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
    if not added:
        return None
    return "\n".join(added)


def _is_private_module_segment(segment: str) -> bool:
    """Return True for a single-underscore implementation module segment."""
    return segment.startswith("_") and not segment.startswith("__")


def _private_module_segments(module_name: str) -> list[str]:
    """Return private segments from a dotted module/import path."""
    return [segment for segment in module_name.split(".") if _is_private_module_segment(segment)]


def _module_path_from_python_file(path_value: str) -> str:
    """Return a dotted module-ish path from a Python file path."""
    normalized = path_value.replace("\\", "/").strip("/")
    if not normalized.endswith((".py", ".pyi")):
        return normalized.replace("/", ".")
    module_path = normalized.rsplit(".", 1)[0].replace("/", ".")
    if module_path.endswith(".__init__"):
        return module_path.removesuffix(".__init__")
    return module_path


def _imported_modules(node: ast.AST) -> list[tuple[int, str]]:
    """Return imported module paths from an import node."""
    if isinstance(node, ast.ImportFrom) and node.module:
        return [(node.lineno, node.module)]
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name) for alias in node.names]
    return []


@final
class PythonPrivateImportChainRule(Rule):
    """Block stacked private module paths/imports such as _orchestrate._core."""

    rule_id = "PY-IMPORT-003"
    title = "Block stacked private Python import chains"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def _finding(
        self,
        ctx: HookContext,
        path_value: str,
        target: str,
        *,
        line: int | None = None,
        kind: str,
    ) -> RuleFinding:
        location = f" on line {line}" if line is not None else ""
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"`{path_value}` introduces a stacked private Python {kind}{location}: "
                f"`{target}`. Avoid names that force imports like "
                "`pkg._impl._core`; expose the API through a facade or use descriptive "
                "public module names."
            ),
            additional_context=(
                "Keep at most one private module segment in an import/path. If a split "
                "needs multiple files, prefer `orchestrate/context.py`, "
                "`orchestrate/platform_auth.py`, etc., and re-export stable names from "
                "the package boundary instead of making callers import nested internals."
            ),
            metadata={"path": path_value, "target": target, "kind": kind, "line": line},
        )

    def _path_finding(self, ctx: HookContext, path_value: str) -> RuleFinding | None:
        module_path = _module_path_from_python_file(path_value)
        if len(_private_module_segments(module_path)) < 2:
            return None
        return self._finding(ctx, path_value, module_path, kind="module path")

    def _import_findings(
        self,
        ctx: HookContext,
        source: str,
        path_value: str,
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            added_source = _patch_added_source(source)
            module = parse_module(added_source or "", ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            for line, module_name in _imported_modules(node):
                if len(_private_module_segments(module_name)) < 2:
                    continue
                findings.append(
                    self._finding(
                        ctx,
                        path_value,
                        module_name,
                        line=line,
                        kind="import chain",
                    )
                )
        return findings

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        path_finding = self._path_finding(ctx, path_value)
        if path_finding is not None:
            findings.append(path_finding)
        findings.extend(self._import_findings(ctx, source, path_value))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonImportAliasRule(Rule):
    """PY-IMPORT-002: Block non-standard import aliases.

    Arbitrary ``as`` aliases let agents make duplicated blocks look different
    enough to evade clone/repeated-block detectors. Keep only well-known library
    coupling aliases such as ``pandas as pd`` or ``polars as pl``.
    """

    rule_id = "PY-IMPORT-002"
    title = "Block non-standard Python import aliases"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _iter_modules(source: str, max_chars: int) -> list[ast.Module]:
        modules: list[ast.Module] = []
        module = parse_module(source, max_chars)
        if module is not None:
            modules.append(module)
            return modules
        added_source = _patch_added_source(source)
        if added_source is None:
            return modules
        added_module = parse_module(added_source, max_chars)
        if added_module is not None:
            modules.append(added_module)
        return modules

    @staticmethod
    def _collect_aliases(module: ast.Module) -> list[tuple[int, str, str, str, str]]:
        aliases: list[tuple[int, str, str, str, str]] = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name in node.names:
                if name.asname is None or _allowed_import_alias(node, name):
                    continue
                replacement, usage = _import_alias_replacement(node, name)
                aliases.append((
                    node.lineno,
                    _import_alias_full_name(node, name),
                    name.asname,
                    replacement,
                    usage,
                ))
        return aliases

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        max_chars = ctx.config.python_ast_max_parse_chars
        for module in self._iter_modules(source, max_chars):
            for lineno, imported_name, asname, replacement, usage in self._collect_aliases(module):
                message = (
                    f"`{path_value}` imports `{imported_name} as {asname}` on line "
                    f"{lineno}. Non-standard import aliases are blocked because "
                    "they hide duplicated code from clone/repeated-block detectors. "
                    "Use the real module/name or extract shared behavior instead. "
                    "Only canonical library aliases are allowed, e.g. `pandas as pd`, "
                    "`polars as pl`, `numpy as np`, or `matplotlib.pyplot as plt`.\n\n"
                    "Use this instead:\n"
                    f"    {replacement}\n"
                    f"Then call: `{usage}`"
                )
                findings.append(
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.HIGH,
                        decision=decision_for_context(ctx),
                        message=message,
                        additional_context=(
                            "Remove the alias or refactor the duplicated block; do "
                            "not rename imports to make duplicate code look unique."
                        ),
                        metadata={
                            "path": path_value,
                            "line": lineno,
                            "imported_name": imported_name,
                            "alias": asname,
                        },
                    )
                )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# PY-IMPORT-001: Import fanout suggests facade opportunity
# ---------------------------------------------------------------------------


@final
class PythonImportFanoutRule(Rule):
    """PY-IMPORT-001: Detect when too many names are imported from one module.

    A high import count from a single module signals that the caller should
    either use a namespace import or that the source module needs a facade.
    """

    rule_id = "PY-IMPORT-001"
    title = "Import fanout suggests facade opportunity"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    @staticmethod
    def _collect_names_by_module(module: ast.Module) -> dict[str, list[str]]:
        """Return mapping of source-module name -> imported names (top-level only)."""
        names_by_module: dict[str, list[str]] = defaultdict(list)
        for node in module.body:
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            for alias in node.names:
                imported_name = alias.asname if alias.asname else alias.name
                names_by_module[node.module].append(imported_name)
        return names_by_module

    def _fanout_finding(
        self, path_value: str, mod_name: str, names: list[str], limit: int
    ) -> RuleFinding | None:
        """Return a finding when import count exceeds limit, else None."""
        if len(names) <= limit:
            return None
        family_prefix = detect_family_prefix(names)
        names_preview = ", ".join(names[:6]) + (", ..." if len(names) > 6 else "")
        if family_prefix is not None:
            severity = Severity.MEDIUM
            family_msg = (
                f" Several names share the `{family_prefix}` prefix"
                " \u2014 strong signal for a service class or facade."
            )
        else:
            severity = Severity.LOW
            family_msg = ""
        message = (
            f"`{path_value}` imports {len(names)} names from `{mod_name}` "
            f"({names_preview}).{family_msg} Advisory only: this is context "
            "for a future dependency-design pass; do not retry the write solely "
            f"for this. Consider `import {mod_name}` and access via namespace, "
            f"or introduce a facade/service class to reduce coupling when the "
            f"module boundary is already in scope."
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=severity,
            decision="context",
            message=message,
            metadata={
                "path": path_value,
                "module": mod_name,
                "import_count": len(names),
                "names": names,
                "family_prefix": family_prefix,
            },
        )

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        limit = ctx.config.python_import_fanout_limit
        names_by_module = self._collect_names_by_module(module)
        findings: list[RuleFinding] = []
        for mod_name, names in names_by_module.items():
            finding = self._fanout_finding(path_value, mod_name, names, limit)
            if finding is not None:
                findings.append(finding)
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
