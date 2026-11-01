"""Known lint ids must survive harmless ``file:line`` drift without hiding new debt."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies

from slopgate.lint import compute_synced_baseline_rules
from slopgate.lint._baseline import Violation
from slopgate.lint.baseline_drift import line_insensitive_id, reconcile_line_drift

RULE = "repeated-magic-number"
PREFIX = f"{RULE}|<project>|16|"
INHERITED = f"{PREFIX}appears in 6 files (max: 5); locations: a.py:11, b.py:27"
SHIFTED = f"{PREFIX}appears in 6 files (max: 5); locations: a.py:11, b.py:28"
GROWN = f"{PREFIX}appears in 7 files (max: 5); locations: a.py:11, b.py:28, c.py:30"
TWIN_A = "rule|p.py|x|appears in 2 files; locations: a.py:1, b.py:2"
TWIN_B = "rule|p.py|x|appears in 2 files; locations: a.py:5, b.py:9"
TWIN_C = "rule|p.py|x|appears in 2 files; locations: a.py:6, b.py:10"


def _violation(stable_id: str) -> Violation:
    rule, relative_path, identifier, detail = stable_id.split("|", 3)
    return Violation(
        rule=rule, relative_path=relative_path, identifier=identifier, detail=detail
    )


@pytest.mark.parametrize(
    ("stable_id", "expected"),
    [
        (
            "r|p.py|n|appears in 6 files (max: 5); locations: a.py:11, b.py:27",
            "r|p.py|n|appears in 6 files (max: 5); locations: a.py, b.py",
        ),
        ("r|<project>|localhost:8080|appears in 6 files", None),
        ("r|p.py|n|appears in 6 files (max: 5)", None),
        (
            'r|<project>|"https://api.example.com:443"'
            "|appears in 6 files (max: 5); locations: a.py:11",
            'r|<project>|"https://api.example.com:443"'
            "|appears in 6 files (max: 5); locations: a.py",
        ),
        (
            "r|p.py|pkg.mod:12|appears in 6 files; locations: a.py:11",
            "r|p.py|pkg.mod:12|appears in 6 files; locations: a.py",
        ),
        (
            'r|<project>|"x"|appears in 6 files; locations: a.py:11'
            "; import existing constant X from pkg/const.py:12"
            "; see https://api.example.com:443",
            'r|<project>|"x"|appears in 6 files; locations: a.py'
            "; import existing constant X from pkg/const.py"
            "; see https://api.example.com:443",
        ),
        ("r|p.py|n|see notes from pkg.mod:12", None),
    ],
    ids=[
        "location-lines-stripped",
        "port-kept",
        "max-count-kept",
        "host-port-literal-kept",
        "dotted-symbol-kept",
        "post-marker-url-kept",
        "no-marker-from-text-kept",
    ],
)
def test_line_insensitive_id_only_strips_path_lines(
    stable_id: str, expected: str | None
) -> None:
    normalized = line_insensitive_id(stable_id)

    assert normalized == (expected or stable_id), f"unexpected id {normalized!r}"


def test_line_insensitive_id_keeps_constant_source_path() -> None:
    stable_id = (
        'r|<project>|"token"|appears in 6 files (max: 5); locations: a.py:11'
        "; import existing constant TOKEN from pkg/const.py:12; do not duplicate it"
    )

    normalized = line_insensitive_id(stable_id)

    assert "a.py:11" not in normalized, (
        f"location line must be dropped, got {normalized!r}"
    )
    assert "const.py:12" not in normalized, (
        f"constant source line must be dropped, got {normalized!r}"
    )
    assert "from pkg/const.py" in normalized, (
        f"constant source path must survive, got {normalized!r}"
    )


@pytest.mark.parametrize(
    ("known", "current", "expected"),
    [
        ({INHERITED}, {SHIFTED}, {SHIFTED}),
        ({INHERITED}, {GROWN}, {INHERITED}),
        ({TWIN_A, TWIN_B}, {TWIN_A, TWIN_B}, {TWIN_A, TWIN_B}),
        ({TWIN_A}, {TWIN_B, TWIN_C}, {TWIN_A}),
    ],
    ids=["moved-debt-adopted", "grown-debt-stays-new", "exact-ids-win", "ambiguous"],
)
def test_reconcile_line_drift_pairs_ids_one_to_one(
    known: set[str], current: set[str], expected: set[str]
) -> None:
    reconciled = reconcile_line_drift({RULE: known}, {RULE: current})

    assert reconciled == {RULE: expected}, f"unexpected reconciliation {reconciled}"


def _drift_id(identifier: str, line: int) -> str:
    return f"rule|p.py|{identifier}|appears in 2 files; locations: a.py:{line}"


_DRIFT_IDS = strategies.sets(
    strategies.builds(
        _drift_id,
        strategies.sampled_from("xy"),
        strategies.integers(min_value=1, max_value=4),
    ),
    max_size=6,
)


@given(known=_DRIFT_IDS, current=_DRIFT_IDS)
def test_reconcile_line_drift_is_a_one_to_one_swap(
    known: set[str], current: set[str]
) -> None:
    reconciled = reconcile_line_drift({RULE: known}, {RULE: current})[RULE]

    assert len(reconciled) == len(known), "a swap must never collapse known ids"
    assert known & current <= reconciled, "exact matches must always be kept"
    assert reconciled <= known | current, "only known or current ids may appear"
    assert reconcile_line_drift({RULE: reconciled}, {RULE: current}) == {
        RULE: reconciled
    }, "reconciling twice must be stable"


def test_prune_only_sync_refreshes_moved_debt_instead_of_pruning() -> None:
    collectors = [(RULE, [_violation(SHIFTED)])]

    synced, removed = compute_synced_baseline_rules(
        collectors, {RULE: {INHERITED}}, prune_only=True
    )

    assert (synced, removed) == ({RULE: {SHIFTED}}, 0), (
        f"expected the moved id refreshed in place, got {synced}, removed={removed}"
    )
