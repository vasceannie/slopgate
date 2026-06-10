"""Scenario-specific guidance for oversized Python module guardrails."""

from __future__ import annotations

from slopgate.util.payloads import lower_path


def module_split_scenario(path_value: str) -> str:
    """Classify an oversized module so hook guidance can be specific."""
    normalized = lower_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    name_scenarios = {"conftest.py": "conftest", "__init__.py": "package-init"}
    if scenario := name_scenarios.get(name):
        return scenario
    if (
        name.startswith("test_")
        or normalized.startswith("tests/")
        or "/tests/" in normalized
    ):
        return "test-module"
    entrypoint_names = {"cli.py", "main.py", "app.py"}
    if name in entrypoint_names or normalized.endswith("/routes.py"):
        return "entrypoint-or-router"
    return "module-to-package"


OVERSIZED_SPLIT_PLANS = {
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


def oversized_module_split_guidance(path_value: str, scenario: str) -> str:
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
    plan = OVERSIZED_SPLIT_PLANS.get(
        scenario, OVERSIZED_SPLIT_PLANS["module-to-package"]
    )
    return f"{plan}\n\n{common}\n{verification}"
