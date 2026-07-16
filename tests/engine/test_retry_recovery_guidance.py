from __future__ import annotations

import pytest

from slopgate.engine import _retry


@pytest.mark.parametrize(
    ("rule_id", "guidance_id"),
    [
        ("PY-CODE-013", "inline-or-boundary"),
        ("PY-IMPORT-002", "canonical-import-alias"),
        ("PY-IMPORT-003", "public-import-facade"),
        ("PY-LOG-002", "boundary-logging"),
        ("PY-CODE-018", "module-package-split"),
        ("QUALITY-LINT-001", "landed-lint-repair"),
        ("SHELL-001", "structured-tool-recovery"),
        ("UNKNOWN-001", "changed-design-generic"),
    ],
    ids=(
        "thin_wrapper",
        "import_alias",
        "private_import",
        "boundary_logging",
        "oversized_module",
        "quality_lint",
        "shell",
        "generic",
    ),
)
def test_rule_specific_recovery_guidance_selects_one_non_conflicting_route(
    rule_id: str, guidance_id: str
) -> None:
    guidance = _retry.recovery_guidance(rule_id)

    assert guidance.guidance_id == guidance_id, (
        "Each retry rule should select its stable recovery route"
    )
    assert guidance.conflicts == (), (
        "A retry response must not recommend conflicting recovery routes"
    )
