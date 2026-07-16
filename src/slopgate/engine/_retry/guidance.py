"""Single-route changed-design guidance for repeated rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecoveryGuidance:
    guidance_id: str
    text: str
    conflicts: tuple[str, ...] = ()


_GENERIC = RecoveryGuidance(
    "changed-design-generic",
    "Change the design, not just the content or tool arguments, before retrying.",
)

_GUIDANCE = {
    "PY-CODE-013": RecoveryGuidance(
        "inline-or-boundary",
        "Inline it, absorb it into the owner, or add real policy or validation.",
    ),
    "PY-IMPORT-002": RecoveryGuidance(
        "canonical-import-alias",
        "Remove invented aliases and use canonical names.",
    ),
    "PY-IMPORT-003": RecoveryGuidance(
        "public-import-facade",
        "Import through the public package facade or move the shared API to a public module.",
    ),
    "PY-LOG-002": RecoveryGuidance(
        "boundary-logging",
        "Identify the actual handoff and reuse existing telemetry.",
    ),
    "PY-CODE-018": RecoveryGuidance(
        "module-package-split",
        "Choose a cohesive module-to-package split with a thin facade; no line shaving or formatting camouflage.",
    ),
    "QUALITY-LINT-001": RecoveryGuidance(
        "landed-lint-repair",
        "Repair only the named collector before resuming feature work.",
    ),
    "SHELL-001": RecoveryGuidance(
        "structured-tool-recovery",
        "Preserve failures and branch only on explicitly expected errors.",
    ),
}


def recovery_guidance(rule_id: str) -> RecoveryGuidance:
    normalized_rule = rule_id.strip().upper()
    selected = _GUIDANCE.get(normalized_rule)
    if selected is None:
        return _GENERIC
    return selected
