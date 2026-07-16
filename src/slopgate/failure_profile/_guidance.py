"""First-write guidance derived from recurring aggregate risks."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict
from slopgate.context import HookContext

from ._models import FailureRisk
from ._store import FailureProfileStore


@dataclass(frozen=True, slots=True)
class _FailureProfileGuidance:
    risks: tuple[FailureRisk, ...]

    @property
    def text(self) -> str:
        labels = ", ".join(
            f"{risk.rule_id} ({risk.path_role}/{risk.language})" for risk in self.risks
        )
        return f"Recurring repository risks to cover in the preflight: {labels}."

    @property
    def metadata(self) -> list[ObjectDict]:
        return [risk.to_json() for risk in self.risks]


def _first_write_profile_guidance(ctx: HookContext) -> _FailureProfileGuidance | None:
    if not ctx.config.failure_profile.enabled:
        return None
    risks = FailureProfileStore(
        ctx.config.trace_dir, ctx.config.repo_root, ctx.config.failure_profile
    ).top_risks()
    return _FailureProfileGuidance(risks) if risks else None


FailureProfileGuidance = _FailureProfileGuidance
first_write_profile_guidance = _first_write_profile_guidance
