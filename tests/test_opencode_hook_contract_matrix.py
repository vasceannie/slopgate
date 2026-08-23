from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from slopgate._types import ObjectDict, object_dict, object_list, string_value


MATRIX_PATH: Final = (
    Path(__file__).with_name("fixtures") / "opencode_hook_contract_matrix.json"
)
HARNESS_SCHEMA_PATH: Final = (
    Path(__file__).with_name("fixtures") / "harness_schema_context.json"
)
REQUIRED_EVIDENCE_TIERS: Final = {
    "documented",
    "typed",
    "pinned-source",
    "local-observed",
    "unresolved",
}
REQUIRED_CASES: Final = {
    "before-args-mutation",
    "before-throw-blocks",
    "ignored-hook-return",
    "after-typed-fields",
    "missing-after-uncertain",
    "independent-outcome-axes",
    "native-session-call-ids",
    "same-worktree-shared-state",
    "separate-worktree-isolation",
    "generation-race",
    "event-properties-envelope",
    "file-edited-reordered-advisory",
    "after-detection-no-prevention",
    "permission-ask-untriggered",
    "system-transform-session-present",
    "system-transform-session-absent",
    "compaction-advisory",
    "unknown-effect-deny",
    "verification-generation-clear",
    "headless-pure-control",
    "headless-plugin-tool-hooks",
    "headless-app-log",
    "stale-version-identity",
}


def _cases() -> list[ObjectDict]:
    matrix = object_dict(json.loads(MATRIX_PATH.read_text(encoding="utf-8")))
    return [object_dict(case) for case in object_list(matrix.get("cases"))]


def _missing_evidence_references() -> list[str]:
    missing: list[str] = []
    for case in _cases():
        test_path = string_value(case.get("test_path"))
        test_name = string_value(case.get("test_name"))
        probe = string_value(case.get("probe"))
        if test_path and test_name:
            source_path = MATRIX_PATH.parents[2] / test_path
            if source_path.exists() and f"def {test_name}" in source_path.read_text(
                encoding="utf-8"
            ):
                continue
        if probe and probe.strip():
            continue
        missing.append(string_value(case.get("id")) or "")
    return missing


def _harness_matrix_reference() -> str | None:
    harness_schema = object_dict(
        json.loads(HARNESS_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    expected_contract = object_dict(harness_schema.get("expected_contract"))
    opencode_contract = object_dict(expected_contract.get("opencode"))
    return string_value(opencode_contract.get("regression_matrix"))


def test_opencode_contract_matrix_covers_required_lifecycle_cases() -> None:
    case_ids = {string_value(case.get("id")) or "" for case in _cases()}

    assert case_ids == REQUIRED_CASES, "OpenCode lifecycle matrix coverage drifted"


def test_opencode_contract_matrix_uses_every_evidence_tier() -> None:
    evidence_tiers = {
        string_value(case.get("evidence_tier")) or "" for case in _cases()
    }

    assert evidence_tiers == REQUIRED_EVIDENCE_TIERS, "evidence tiers lost coverage"


def test_unresolved_headless_plugin_tool_probe_is_not_public() -> None:
    headless = next(
        case for case in _cases() if case.get("id") == "headless-plugin-tool-hooks"
    )

    assert headless["evidence_tier"] == "unresolved", (
        "headless plugin-tool anomaly must remain unresolved"
    )
    assert headless["status"] == "unresolved", (
        "unresolved headless probe cannot claim support"
    )
    assert headless["public_contract"] is False, (
        "unresolved observations cannot become public contracts"
    )


def test_matrix_references_executable_tests_or_probe_commands() -> None:
    missing = _missing_evidence_references()

    assert missing == [], f"matrix rows lack executable evidence: {missing}"


def test_harness_schema_context_points_to_opencode_regression_matrix() -> None:
    assert _harness_matrix_reference() == (
        "tests/fixtures/opencode_hook_contract_matrix.json"
    ), "harness schema must link its executable OpenCode evidence matrix"
