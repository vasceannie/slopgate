from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from slopgate._types import object_dict, object_list

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
BASELINE_PATH: Final = REPO_ROOT / "tests" / "fixtures" / "dashboard_pi_analogues.json"
DOC_PATH: Final = REPO_ROOT / "docs" / "adapters" / "omp.md"
HARNESS_STATUS_PATH: Final = (
    "dashboard/scripts/forcedash_server/remote_scripts/harness_status.py.txt"
)
TYPES_PATH: Final = "dashboard/src/types/slopgate.ts"
MANDATORY_PATHS: Final = {
    "dashboard/src/types/slopgate.ts",
    "dashboard/scripts/build_standalone/projection.py",
    "dashboard/scripts/forcedash_server/remote_scripts/trace_snapshot.py.txt",
    "dashboard/tailwind.config.ts",
    "dashboard/src/index.css",
    "dashboard/src/lib/chartTheme.ts",
    "dashboard/src/context/traceRecordValidation.ts",
    "dashboard/src/components/dashboard/TimeWindowSelector.tsx",
    "dashboard/src/components/dashboard/DecisionFunnel.tsx",
    "dashboard/src/data/mockTraces.ts",
}


@dataclass(frozen=True, slots=True)
class TokenSpec:
    token_class: str
    pi_pattern: re.Pattern[str]
    omp_pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class Occurrence:
    path: str
    token_class: str
    matched_text: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class InventoryRow:
    path: str
    token_class: str
    matched_text: str
    count: int
    ordinals: tuple[int, ...]


TOKEN_SPECS: Final = (
    TokenSpec("quoted_pi", re.compile(r'["\x27]pi["\x27]'), re.compile(r'["\x27]omp["\x27]')),
    TokenSpec("quoted_Pi", re.compile(r'["\x27]Pi["\x27]'), re.compile(r'["\x27]OMP["\x27]')),
    TokenSpec("bare_pi_key", re.compile(r"(?<![\w-])pi\s*:"), re.compile(r"(?<![\w-])omp\s*:")),
    TokenSpec("double_dash_platform_pi", re.compile(r"--platform-pi"), re.compile(r"--platform-omp")),
    TokenSpec("platform_pi", re.compile(r"(?<!--)platform-pi"), re.compile(r"(?<!--)platform-omp")),
)


def _source_paths() -> tuple[Path, ...]:
    src_paths = (
        path
        for path in (REPO_ROOT / "dashboard" / "src").rglob("*")
        if path.is_file() and path.suffix in {".ts", ".tsx", ".css"}
    )
    script_paths = (
        path
        for path in (REPO_ROOT / "dashboard" / "scripts").rglob("*")
        if path.is_file() and path.name.endswith((".py", ".py.txt"))
    )
    tailwind_path = REPO_ROOT / "dashboard" / "tailwind.config.ts"
    return tuple(sorted((*src_paths, *script_paths, tailwind_path)))


def _scan(pattern_kind: str) -> tuple[Occurrence, ...]:
    occurrences: list[Occurrence] = []
    for path in _source_paths():
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        for spec in TOKEN_SPECS:
            pattern = spec.pi_pattern if pattern_kind == "pi" else spec.omp_pattern
            occurrences.extend(
                Occurrence(relative_path, spec.token_class, match.group(0), ordinal)
                for ordinal, match in enumerate(pattern.finditer(text), start=1)
            )
    return tuple(occurrences)


def _inventory_rows(occurrences: tuple[Occurrence, ...]) -> tuple[InventoryRow, ...]:
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for occurrence in occurrences:
        key = (occurrence.path, occurrence.token_class, occurrence.matched_text)
        grouped.setdefault(key, []).append(occurrence.ordinal)
    return tuple(
        InventoryRow(path, token_class, matched_text, len(ordinals), tuple(ordinals))
        for (path, token_class, matched_text), ordinals in sorted(grouped.items())
    )


def _load_baseline() -> tuple[InventoryRow, ...]:
    payload = object_dict(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
    rows: list[InventoryRow] = []
    for raw_item in object_list(payload.get("occurrences")):
        item = object_dict(raw_item)
        path = item.get("path")
        token_class = item.get("token_class")
        matched_text = item.get("matched_text")
        count = item.get("count")
        ordinals = object_list(item.get("ordinals"))
        assert isinstance(path, str)
        assert isinstance(token_class, str)
        assert isinstance(matched_text, str)
        assert isinstance(count, int)
        assert all(isinstance(ordinal, int) for ordinal in ordinals)
        rows.append(
            InventoryRow(
                path,
                token_class,
                matched_text,
                count,
                tuple(ordinal for ordinal in ordinals if isinstance(ordinal, int)),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.path, row.token_class, row.matched_text)))


def _is_deferred(occurrence: Occurrence) -> bool:
    if occurrence.path == HARNESS_STATUS_PATH:
        return True
    return occurrence == Occurrence(TYPES_PATH, "quoted_pi", '"pi"', 2)


def _dashboard_deferral_selectors() -> set[str]:
    document = DOC_PATH.read_text(encoding="utf-8")
    deferral_section = document.partition("## Dashboard deferrals")[2].partition("\n## ")[0]
    return {
        line.split("|")[1].strip().strip("`")
        for line in deferral_section.splitlines()
        if line.startswith("| `")
    }


def test_dashboard_pi_inventory_remains_byte_token_equivalent_to_baseline() -> None:
    assert _inventory_rows(_scan("pi")) == _load_baseline(), (
        "Dashboard Pi token occurrences must remain unchanged from the Todo-5 base SHA"
    )


def test_dashboard_omp_counterparts_match_every_mandatory_pi_occurrence() -> None:
    pi_occurrences = _scan("pi")
    mandatory_pi = tuple(occurrence for occurrence in pi_occurrences if not _is_deferred(occurrence))
    required_counts = Counter((occurrence.path, occurrence.token_class) for occurrence in mandatory_pi)
    observed_counts = Counter((occurrence.path, occurrence.token_class) for occurrence in _scan("omp"))

    assert {path for path, _token_class in required_counts} == MANDATORY_PATHS, (
        "Automatic classification must resolve exactly the ten mandatory dashboard files"
    )
    assert observed_counts == required_counts, (
        "Each mandatory Pi token needs one OMP counterpart, while deferred selectors need none"
    )


def test_omp_docs_list_exactly_the_two_dashboard_deferrals() -> None:
    assert _dashboard_deferral_selectors() == {"HarnessPlatformStatus.id", HARNESS_STATUS_PATH}, (
        "OMP adapter docs must list exactly the two dashboard harness-status deferrals"
    )
