"""State-backed first-write contract rule."""

from __future__ import annotations

import shlex
from pathlib import Path

from slopgate.constants import (
    BLOCK,
    CONTEXT,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    WARN,
)
from slopgate.context import HookContext
from slopgate.failure_profile import (
    FailureProfileGuidance,
    first_write_profile_guidance,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule
from slopgate.state import (
    FIRST_WRITE_CONTRACT_SCHEMA_VERSION,
    FIRST_WRITE_RISK_MAX,
    FIRST_WRITE_RISK_MIN,
    FirstWriteContractCheck,
    normalize_contract_operation,
    normalize_contract_target,
)
from slopgate.util.payloads import is_edit_like_tool


class _FirstWriteContractRule(Rule):
    rule_id = "WORKFLOW-FIRST-WRITE-001"
    title = "State-backed first-write contract"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _targets(ctx: HookContext) -> list[str]:
        cwd = Path(ctx.cwd)
        return list(
            dict.fromkeys(
                normalize_contract_target(path, cwd)
                for path in ctx.candidate_paths
                if path.strip()
            )
        )

    @staticmethod
    def _surface_action(ctx: HookContext) -> str | None:
        surface = ctx.config.rule_surfaces.get(_FirstWriteContractRule.rule_id)
        return surface.hook.action if surface is not None else None

    @staticmethod
    def _finding_metadata(
        check: FirstWriteContractCheck,
        action: str | None,
        record_command: list[str],
        profile_guidance: FailureProfileGuidance | None,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "target": check.target,
            "operation": check.operation,
            "contract_status": check.status,
            "missing_fields": list(check.missing_fields),
            "required_risk_range": [FIRST_WRITE_RISK_MIN, FIRST_WRITE_RISK_MAX],
            "record_command": record_command,
            "schema_version": FIRST_WRITE_CONTRACT_SCHEMA_VERSION,
            "rollout": "shadow" if action is None else action,
        }
        if profile_guidance is not None:
            metadata["aggregate_failure_risks"] = profile_guidance.metadata
        return metadata

    def _missing_finding(
        self, ctx: HookContext, check: FirstWriteContractCheck, action: str | None
    ) -> RuleFinding:
        blocking = action in {BLOCK, DENY}
        context_enabled = action in {BLOCK, CONTEXT, DENY, WARN, "ask"}
        missing = ", ".join(check.missing_fields)
        record_command = [
            "slopgate",
            "contract",
            "record",
            "--session-id",
            ctx.session_id,
            "--target",
            check.target,
            "--operation",
            check.operation,
        ]
        context = None
        if context_enabled:
            context = (
                f"First-write contract missing for {check.target}. Missing fields: "
                f"{missing}. Include {FIRST_WRITE_RISK_MIN}-{FIRST_WRITE_RISK_MAX} "
                "predicted risks and record it with "
                f"`{shlex.join(record_command)} ...`."
            )
        profile_guidance = (
            first_write_profile_guidance(ctx) if context_enabled else None
        )
        if context is not None and profile_guidance is not None:
            context = f"{context}\n\n{profile_guidance.text}"
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH if blocking else Severity.MEDIUM,
            decision=DENY if blocking else None,
            message=f"First-write contract is incomplete for {check.target}: {missing}",
            additional_context=context,
            metadata=self._finding_metadata(
                check, action, record_command, profile_guidance
            ),
        )

    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_edit_like_tool(ctx.tool_name):
            return []
        targets = self._targets(ctx)
        if not targets:
            return []
        operation = normalize_contract_operation(ctx.tool_name)
        if ctx.event_name == POST_TOOL_USE:
            ctx.state.finalize_first_write_contracts(ctx.session_id, targets, operation)
            return []
        checks = ctx.state.authorize_first_write_contracts(
            ctx.session_id, targets, operation
        )
        action = self._surface_action(ctx)
        return [
            self._missing_finding(ctx, check, action)
            for check in checks
            if not check.complete
        ]


FirstWriteContractRule = _FirstWriteContractRule
