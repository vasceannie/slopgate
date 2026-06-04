from __future__ import annotations

from slopgate._types import object_dict, object_list, string_value
from slopgate.constants import (
    DENY,
    METADATA_PATH,
    POST_TOOL_USE,
    PRODUCTION_SYMBOL_PREVIEW_LIMIT,
)
from slopgate.context import HookContext
from slopgate.models import RuleFinding
from slopgate.util.path_filters import is_third_party_or_virtualenv_path

_REPLAN_PROMPT = (
    "If a hook denies or blocks your change, do not immediately retry the same edit pattern. "
    "Classify the failure first: structural, policy/tooling, or quality. Change approach before retrying. "
    "If the same file or rule is denied twice, stop and make a short repair plan before the next write. "
    "Prefer small helper extractions, params objects, and named constants over large rewrites."
)

_RULE_HINTS: dict[str, str] = {
    "PY-AST-001": (
        "Next step: stop refactoring; restore parseability with a full reread "
        "plus `python3 -m py_compile <file>`."
    ),
    "PY-CODE-008": "Next step: extract one helper first; avoid full-file rewrites.",
    "PY-CODE-010": (
        "Next step: break the executable expression or extract an intermediate variable. "
        "The line-length hook ignores docstrings/string literals and whitespace-only "
        "padding, so do not mangle docs or spacing to appease it."
    ),
    "PY-CODE-011": (
        "Next step: use guard clauses or extract the inner branch before "
        "adding more conditionals."
    ),
    "PY-CODE-013": (
        "Recovery skill: load `code-hygiene-refactor` before retrying. "
        "Next step: inline pass-throughs unless the wrapper owns a real "
        "domain boundary. A real wrapper does at least one job: validates/normalizes "
        "inputs, changes abstraction level with a domain name, centralizes policy, "
        "caching, permission, or logging, adapts one interface to another, or hides "
        "unstable third-party API details. If it is a real boundary, make the "
        "behavior explicit in the body/name; otherwise replace calls with the target "
        "and delete the wrapper."
    ),
    "PY-CODE-014": (
        "Next step: split the class by responsibility into composed "
        "collaborators, not random method moves."
    ),
    "PY-CODE-015": (
        "Next step: replace branch chains with named predicates or dispatch "
        "before adding behavior."
    ),
    "PY-CODE-017": (
        "Recovery skill: load `code-hygiene-refactor` before retrying. Read the "
        "quality/architecture and python/project-structure rule shards. Convert "
        "flat `prefix_*.py` siblings into a `prefix/` package with a small "
        "`__init__.py` facade/re-export layer; do not add another flat sibling."
    ),
    "PY-CODE-018": (
        "Recovery skill: load `code-hygiene-refactor` before retrying; if the "
        "repair spans many files, switch to `hygiene-orchestrator`. Next step: "
        "choose a split shape first: conftest registry/support modules, "
        "module-to-package facade, thin __init__.py, CLI/router-to-services, "
        "test-module split, or data/resources extraction; do no line shaving."
    ),
    "PY-TEST-003": (
        "Next step: convert loops-with-asserts into pytest parametrization "
        "with readable ids."
    ),
    "PY-TEST-004": "Next step: move shared fixtures into the narrowest useful conftest.py.",
    "PY-TYPE-002": (
        "Next step: remove the suppression and add a Protocol, TypedDict, "
        "overload, or local stub."
    ),
    "PY-QUALITY-005": (
        "Next step: catch the specific expected empty case; propagate "
        "corruption/infrastructure failures."
    ),
    "PY-QUALITY-010": (
        "Next step: define UPPER_CASE constants first, then replace "
        "repeated literals."
    ),
    "GLOBAL-BUILTIN-SYSTEM-PROTECTION": (
        "Next step: do not touch protected system paths as file targets. "
        "Executable-position paths like `/usr/bin/rg` are allowed; if this "
        "was /dev/null suppression, handle stderr explicitly instead."
    ),
    "GLOBAL-BUILTIN-HOOK-INFRA-EXEC": (
        "Next step: treat hook infrastructure as read-only unless Trav "
        "explicitly approved this edit."
    ),
    "QA-PATH-003": (
        "Next step: do not edit quality tests. Fix the source rule implementation "
        "under `src/slopgate/...`; if expected output legitimately changed, "
        "update only `tests/quality/baselines.json`, then run "
        "`python -m pytest -q tests/quality`."
    ),
    "SHELL-001": (
        "Do not run shell retries. Next step: use structured read/edit/write "
        "tools or handle failures explicitly."
    ),
    "PY-SHELL-001": "Do not run shell retries. Next step: use structured tools.",
}


def _is_test_path(path_value: str | None) -> bool:
    if path_value is None:
        return False
    normalized = path_value.replace("\\", "/")
    return normalized.startswith("tests/") or "/tests/" in normalized


def _quality_lint_hint(ctx: HookContext, item: RuleFinding) -> str:
    phase_note = ""
    if ctx.event_name == POST_TOOL_USE:
        phase_note = "PostToolUse already-mutated repair protocol: "
    path = _finding_path(item)
    pathless_note = ""
    if path is None:
        pathless_note = (
            " Path was not extracted from the tool payload. Use the file you just "
            "wrote/edited; do not blindly rerun the same patch."
        )
    hint = (
        f"{phase_note}The edit landed, but touched-file lint found quality debt. "
        "Do not continue feature work. Next action: 1) reread the touched file, "
        "2) fix only the reported collector/hit, 3) verify from the project root "
        "with the smallest repo-root quality command: "
        "from the repo root, run `slopgate lint check` (no file/path argument), "
        "4) if no path is available, inspect the last edited file from tool context."
        f"{pathless_note}"
    )
    if _quality_lint_has_oversized_module(item):
        hint = (
            f"{hint} Recovery skill: load `code-hygiene-refactor` before retrying; "
            "if the repair spans many files, switch to `hygiene-orchestrator`. "
            "Use the oversized-module split playbook instead of patching around "
            "line-count symptoms."
        )
    if _quality_lint_has_collector(item, "untested-production-code"):
        hint = f"{hint} {_untested_production_code_hint(item)}"
    return hint


_QUALITY_SYMBOL_KEYS = {
    "symbol",
    "symbols",
    "function",
    "functions",
    "function_names",
    "public_symbols",
    "unreferenced_symbols",
    "untested_symbols",
}


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _flatten_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in object_dict(value).values():
            flattened.extend(_flatten_strings(item))
        return flattened
    flattened = []
    for item in object_list(value):
        flattened.extend(_flatten_strings(item))
    return flattened


def _quality_lint_symbols(item: RuleFinding) -> list[str]:
    symbols: list[str] = []
    metadata = item.metadata
    for key in _QUALITY_SYMBOL_KEYS:
        for value in _flatten_strings(metadata.get(key)):
            _append_unique(symbols, value)
    for hit in object_list(metadata.get("hits")):
        hit_data = object_dict(hit)
        for key in _QUALITY_SYMBOL_KEYS:
            for value in _flatten_strings(hit_data.get(key)):
                _append_unique(symbols, value)
    return symbols[:PRODUCTION_SYMBOL_PREVIEW_LIMIT]


def _quality_lint_paths(item: RuleFinding) -> list[str]:
    paths: list[str] = []
    path = _finding_path(item)
    if path:
        _append_unique(paths, path)
    for value in _flatten_strings(item.metadata.get("paths")):
        display_path = _quality_display_path(value)
        if display_path:
            _append_unique(paths, display_path)
    for hit in object_list(item.metadata.get("hits")):
        hit_path = string_value(object_dict(hit).get(METADATA_PATH))
        display_path = _quality_display_path(hit_path)
        if display_path:
            _append_unique(paths, display_path)
    return paths[:PRODUCTION_SYMBOL_PREVIEW_LIMIT]


def _preview_label(label: str, values: list[str]) -> str:
    if not values:
        return ""
    shown = ", ".join(f"`{value}`" for value in values)
    return f" {label}: {shown}."


def _untested_production_code_hint(item: RuleFinding) -> str:
    return (
        "Untested-production-code unblock: add or update the nearest "
        "behavior/integration tests for the reported production surface first."
        f"{_preview_label('Paths', _quality_lint_paths(item))}"
        f"{_preview_label('Symbols', _quality_lint_symbols(item))} "
        "Run the focused pytest target you changed, then, from the repo root, run "
        "`slopgate lint check` with no file/path argument."
    )


def _quality_lint_has_oversized_module(item: RuleFinding) -> bool:
    return _quality_lint_has_collector_prefix(
        item, ("oversized-module:", "oversized-module-soft:")
    )


def _quality_lint_has_collector(item: RuleFinding, collector_name: str) -> bool:
    return _quality_lint_has_collector_prefix(item, (f"{collector_name}:",))


def _quality_lint_has_collector_prefix(
    item: RuleFinding, prefixes: tuple[str, ...]
) -> bool:
    collectors = object_list(item.metadata.get("failing_collectors"))
    return any(
        isinstance(collector, str) and collector.startswith(prefixes)
        for collector in collectors
    )


def _long_params_hint(item: RuleFinding) -> str:
    path = _finding_path(item)
    if _is_test_path(path):
        return (
            "Next step: this test helper is pretending to be a constructor. Prefer "
            "a named Case dataclass or builder defaults so each test only overrides "
            "the meaningful fields. Forwarding every arg to another constructor is "
            "still too many params."
        )
    return (
        "Next step: group by semantic meaning, not arbitrary parameter bags. "
        "Introduce a typed params object, dataclass, or TypedDict only when the "
        "fields travel together as one concept."
    )


def _rule_hint(ctx: HookContext, item: RuleFinding) -> str | None:
    if item.rule_id == "QUALITY-LINT-001":
        return _quality_lint_hint(ctx, item)
    if item.rule_id == "PY-CODE-009":
        return _long_params_hint(item)
    return _RULE_HINTS.get(item.rule_id)


def _failure_class(rule_id: str) -> str:
    if rule_id.startswith("PY-CODE") or rule_id.startswith("PY-QUALITY"):
        return "structural" if rule_id.startswith("PY-CODE") else "quality"
    if "SHELL" in rule_id or rule_id.startswith("GIT-"):
        return "policy_tooling"
    return "quality"


def _finding_path(item: RuleFinding) -> str | None:
    path = item.metadata.get(METADATA_PATH)
    if isinstance(path, str) and path:
        display_path = _quality_display_path(path)
        if display_path is None:
            return _first_hit_path(item)
        return display_path
    return None


def _quality_display_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    lowered = normalized.lower()
    if lowered in {"content", "patch.diff"}:
        return None
    if is_third_party_or_virtualenv_path(normalized):
        return None
    return path_value


def _first_hit_path(item: RuleFinding) -> str | None:
    for hit in object_list(item.metadata.get("hits")):
        if isinstance(hit, str) and hit and hit != "content":
            display_path = _quality_display_path(hit)
            if display_path:
                return display_path
        if isinstance(hit, dict):
            hit_path = string_value(object_dict(hit).get(METADATA_PATH))
            display_path = _quality_display_path(hit_path)
            if display_path:
                return display_path
    return None


def _denial_context(ctx: HookContext, item: RuleFinding, repeat_count: int) -> str:
    parts = [
        f"Hook phase: {ctx.event_name}",
        f"tool: {ctx.tool_name or 'unknown'}",
        f"failure class: {_failure_class(item.rule_id)}",
    ]
    path = _finding_path(item)
    if path:
        parts.append(f"target: {path}")
        if item.metadata.get(METADATA_PATH) == "content":
            parts.append(f"patch content touched: {path}")
    if repeat_count >= 2:
        parts.append(f"repeat count: {repeat_count}")
    return "; ".join(parts) + "."


def _denial_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in findings if item.decision in {DENY, "block"}]


def _retry_budget_relevant_denials(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in _denial_findings(findings) if item.rule_id != "RETRY-BUDGET-001"]
