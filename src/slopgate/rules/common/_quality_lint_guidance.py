from __future__ import annotations

import shlex

from slopgate.constants import PRODUCTION_SYMBOL_PREVIEW_LIMIT, PYTEST_TEST_PREFIX


def _lint_target_summary(paths: list[str]) -> str:
    if not paths:
        return ""
    shown = ", ".join(paths[:3])
    if len(paths) > 3:
        shown += f", +{len(paths) - 3} more"
    return f" for {shown}"


def _lint_check_instruction(paths: list[str]) -> str:
    command = "from the repo root, run `slopgate lint check`"
    if not paths:
        return f"Run {command} for details."
    shown = ", ".join(shlex.quote(path) for path in paths[:PRODUCTION_SYMBOL_PREVIEW_LIMIT])
    return (
        f"Touched lint candidates: {shown}. {command}; "
        "the command intentionally accepts no file/path argument."
    )


_OVERSIZED_LINT_RULES = ("oversized-module", "oversized-module-soft")


def _has_oversized_module_failure(failures: list[str]) -> bool:
    return any(item.startswith(rule + ":") for item in failures for rule in _OVERSIZED_LINT_RULES)


def _first_lint_path(paths: list[str]) -> str:
    return paths[0] if paths else "<touched .py file>"


def _lint_split_scenario(path_value: str) -> str:
    normalized = path_value.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    if name == "conftest.py":
        return "conftest"
    if name == "__init__.py":
        return "package-init"
    if name.startswith(PYTEST_TEST_PREFIX) or normalized.startswith("tests/") or "/tests/" in normalized:
        return "test-module"
    if name in {"cli.py", "main.py", "app.py"} or normalized.endswith("/routes.py"):
        return "entrypoint-or-router"
    return "module-to-package"


_DEFAULT_SPLIT_DETAIL = (
    "Module/package split: convert module.py into module/__init__.py plus focused "
    "siblings; re-export the old public API; split into models/types, parsing, "
    "services/orchestration, adapters/IO, constants/data, and errors."
)

_SPLIT_SCENARIO_DETAILS = {
    "conftest": (
        "Conftest split: keep conftest.py as a thin fixture registry; move "
        "factories, fake clients/apps, pilot/wait helpers, and assertion helpers "
        "into tests/<area>/support/ modules; move subtree-only fixtures into "
        "that subtree's conftest.py."
    ),
    "package-init": (
        "Package-init split: make __init__.py facade-only with __all__ and "
        "compatibility re-exports; move implementation and import-time side "
        "effects into sibling modules."
    ),
    "test-module": (
        "Test-module split: split by behavior under test; move reusable "
        "factories/fakes/assertion helpers to support modules; use pytest "
        "parametrization for repeated scenarios."
    ),
    "entrypoint-or-router": (
        "Entrypoint/router split: keep commands/routes thin; move orchestration "
        "to services, schemas/models to dedicated modules, and IO adapters to edges."
    ),
}


def _post_lint_split_detail(scenario: str) -> str:
    return _SPLIT_SCENARIO_DETAILS.get(scenario, _DEFAULT_SPLIT_DETAIL)


def _post_lint_oversized_guidance(paths: list[str]) -> str:
    target = _first_lint_path(paths)
    scenario = _lint_split_scenario(target)
    return (
        f"Oversized-module recovery: use the {scenario} split plan before continuing. "
        f"{_post_lint_split_detail(scenario)} "
        "Line-count camouflage is not recovery: do not delete blank lines, compress "
        "formatting, or shuffle comments just to duck the threshold; ruff/formatters "
        "will normalize style while the oversized-module design smell remains. "
        "If the file is mostly generated data or giant literals, move data into "
        "resources, fixtures, or builders instead of hiding it in Python code. "
        f"Verify with `python3 -m py_compile {target}` plus the smallest focused tests."
    )
