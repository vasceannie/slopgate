from __future__ import annotations

REPLAN_PROMPT = (
    "If a hook denies or blocks your change, do not immediately retry the same edit pattern. "
    "Classify the failure first: structural, policy/tooling, or quality. Change approach before retrying. "
    "If the same file or rule is denied twice, stop and make a short repair plan before the next write. "
    "Prefer small helper extractions, params objects, and named constants over large rewrites."
)

RULE_HINTS: dict[str, str] = {
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
        "Recovery skill: load `code-hygiene-refactor` before retrying. "
        "Next step: split the class by responsibility into composed "
        "collaborators, not random method moves."
    ),
    "PY-CODE-015": (
        "Recovery skill: load `code-hygiene-refactor` before retrying. "
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
        "test-module split, or data/resources extraction; do no line shaving. "
        "Visible split plan: create a package directory with a small __init__.py "
        "re-export facade, then move cohesive implementation into named modules."
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
        "Next step: define UPPER_CASE constants first, then replace repeated literals."
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

QUALITY_COLLECTOR_HINTS: dict[str, str] = {
    "oversized-module": (
        "Recovery skill: load `code-hygiene-refactor`; use the module-to-package "
        "split playbook before editing around line-count symptoms."
    ),
    "oversized-module-soft": (
        "Recovery skill: load `code-hygiene-refactor`; split the module before "
        "adding more behavior."
    ),
    "untested-production-code": (
        "Recovery skill: load `test-extender`; add behavior/integration coverage "
        "for the reported production symbols."
    ),
    "missing-integration-test": (
        "Recovery skill: load `test-extender`; add a contract/integration test "
        "across the reported seam."
    ),
    "duplicate-call-sequence": (
        "Recovery skill: load `code-smell-utility-locator`; find the existing "
        "owner before extracting a shared helper."
    ),
    "unnecessary-wrapper": (
        "Recovery skill: load `code-hygiene-refactor`; inline pass-through "
        "wrappers unless they own a real boundary."
    ),
}
