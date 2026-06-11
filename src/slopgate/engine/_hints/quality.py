from __future__ import annotations

from slopgate._types import object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH, POST_TOOL_USE, PRODUCTION_SYMBOL_PREVIEW_LIMIT
from slopgate.context import HookContext
from slopgate.models import RuleFinding

from .constants import QUALITY_COLLECTOR_HINTS
from .paths import finding_path, quality_display_path

QUALITY_SYMBOL_KEYS = {
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
    obj_dict = object_dict(value)
    if obj_dict:
        flattened: list[str] = []
        for item in obj_dict.values():
            flattened.extend(_flatten_strings(item))
        return flattened
    flattened = []
    for item in object_list(value):
        flattened.extend(_flatten_strings(item))
    return flattened


def _quality_lint_symbols(item: RuleFinding) -> list[str]:
    symbols: list[str] = []
    metadata = item.metadata
    for key in QUALITY_SYMBOL_KEYS:
        for value in _flatten_strings(metadata.get(key)):
            _append_unique(symbols, value)
    for hit in object_list(metadata.get("hits")):
        hit_data = object_dict(hit)
        for key in QUALITY_SYMBOL_KEYS:
            for value in _flatten_strings(hit_data.get(key)):
                _append_unique(symbols, value)
    return symbols[:PRODUCTION_SYMBOL_PREVIEW_LIMIT]


def _quality_lint_paths(item: RuleFinding) -> list[str]:
    paths: list[str] = []
    path = finding_path(item)
    if path:
        _append_unique(paths, path)
    for value in _flatten_strings(item.metadata.get("paths")):
        display_path = quality_display_path(value)
        if display_path:
            _append_unique(paths, display_path)
    for hit in object_list(item.metadata.get("hits")):
        hit_path = string_value(object_dict(hit).get(METADATA_PATH))
        display_path = quality_display_path(hit_path)
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


def _quality_lint_has_collector_prefix(
    item: RuleFinding, prefixes: tuple[str, ...]
) -> bool:
    collectors = object_list(item.metadata.get("failing_collectors"))
    return any(
        isinstance(collector, str) and collector.startswith(prefixes)
        for collector in collectors
    )


def _collector_recovery_hints(item: RuleFinding) -> list[str]:
    hints: list[str] = []
    for collector in object_list(item.metadata.get("failing_collectors")):
        if not isinstance(collector, str):
            continue
        collector_name = collector.split(":", 1)[0]
        hint = QUALITY_COLLECTOR_HINTS.get(collector_name)
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def quality_lint_hint(ctx: HookContext, item: RuleFinding) -> str:
    phase_note = ""
    if ctx.event_name == POST_TOOL_USE:
        phase_note = "PostToolUse already-mutated repair protocol: "
    pathless_note = ""
    if finding_path(item) is None:
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
    if _quality_lint_has_collector_prefix(
        item, ("oversized-module:", "oversized-module-soft:")
    ):
        hint = (
            f"{hint} Recovery skill: load `code-hygiene-refactor` before retrying; "
            "if the repair spans many files, switch to `hygiene-orchestrator`. "
            "Use the oversized-module split playbook instead of patching around "
            "line-count symptoms."
        )
    collector_hints = _collector_recovery_hints(item)
    if collector_hints:
        hint = f"{hint} Collector recovery routes: {' '.join(collector_hints)}"
    if _quality_lint_has_collector_prefix(item, ("untested-production-code:",)):
        hint = f"{hint} {_untested_production_code_hint(item)}"
    return hint
