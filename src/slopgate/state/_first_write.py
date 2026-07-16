"""State-backed first-write contract storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Final

from slopgate._types import ObjectDict, ObjectMapping, object_dict, object_list

from ._files import StateSnapshotMixin
from ._models import (
    FirstWriteContractCheck,
    FirstWriteContractDraft,
    FirstWriteContractRecord,
)


FIRST_WRITE_CONTRACT_SCHEMA_VERSION: Final = 1
FIRST_WRITE_RISK_MIN: Final = 3
FIRST_WRITE_RISK_MAX: Final = 5
FIRST_WRITE_REQUIRED_FIELDS: Final = (
    "target",
    "operation",
    "reuse_convention",
    "stable_behavior_api",
    "predicted_risks",
    "design_response",
    "focused_verification",
    "timestamp",
    "schema_version",
)
_INVALID_STATUSES: Final = frozenset({"expired", "schema_version", "malformed"})
_OPERATION_ALIASES: Final = {
    "applypatch": "apply_patch",
    "multiedit": "multi_edit",
    "notebookedit": "notebook_edit",
}


@dataclass(frozen=True, slots=True)
class _ContractIdentity:
    target: str
    operation: str
    now: int


def normalize_contract_target(target: str, cwd: Path) -> str:
    candidate = Path(target.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return str(candidate.resolve(strict=False))
    except OSError:
        return str(candidate.absolute())


def normalize_contract_operation(operation: str) -> str:
    normalized = operation.strip().lower().replace("-", "_").replace(" ", "_")
    return _OPERATION_ALIASES.get(normalized, normalized)


class FirstWriteContractStateMixin(StateSnapshotMixin):
    _TTL_SECONDS: int

    @staticmethod
    def _contract_key(session_id: str, target: str) -> str:
        return json.dumps(
            {"session_id": session_id.strip(), "target": target}, sort_keys=True
        )

    @staticmethod
    def _string_missing(raw: ObjectMapping, field: str) -> bool:
        value = raw.get(field)
        return not isinstance(value, str) or not value.strip()

    def _header_problem(
        self, raw: ObjectMapping, identity: _ContractIdentity
    ) -> FirstWriteContractCheck | None:
        if raw.get("schema_version") != FIRST_WRITE_CONTRACT_SCHEMA_VERSION:
            return FirstWriteContractCheck(
                identity.target,
                identity.operation,
                "schema_version",
                ("schema_version",),
            )
        timestamp = raw.get("timestamp")
        if (
            not isinstance(timestamp, int)
            or timestamp < identity.now - self._TTL_SECONDS
        ):
            return FirstWriteContractCheck(
                identity.target, identity.operation, "expired", ("timestamp",)
            )
        return None

    def _missing_contract_fields(
        self, raw: ObjectMapping, identity: _ContractIdentity
    ) -> tuple[str, ...]:
        fields = (
            "target",
            "operation",
            "reuse_convention",
            "stable_behavior_api",
            "design_response",
            "focused_verification",
        )
        missing = [field for field in fields if self._string_missing(raw, field)]
        risks = [
            item
            for item in object_list(raw.get("predicted_risks"))
            if isinstance(item, str)
        ]
        if not FIRST_WRITE_RISK_MIN <= len(risks) <= FIRST_WRITE_RISK_MAX:
            missing.append("predicted_risks")
        if raw.get("target") != identity.target:
            missing.append("target")
        if raw.get("operation") != identity.operation:
            missing.append("operation")
        return tuple(dict.fromkeys(missing))

    def _check_entry(
        self, raw_entry: ObjectMapping | None, identity: _ContractIdentity
    ) -> FirstWriteContractCheck:
        if raw_entry is None:
            return FirstWriteContractCheck(
                identity.target,
                identity.operation,
                "missing",
                FIRST_WRITE_REQUIRED_FIELDS,
            )
        raw = object_dict(raw_entry)
        header_problem = self._header_problem(raw, identity)
        if header_problem is not None:
            return header_problem
        missing = self._missing_contract_fields(raw, identity)
        if missing:
            status = "malformed" if len(missing) > 1 else next(iter(missing))
            return FirstWriteContractCheck(
                identity.target, identity.operation, status, missing
            )
        authorized = isinstance(raw.get("authorized_at"), int)
        status = "authorized" if authorized else "ready"
        return FirstWriteContractCheck(
            identity.target, identity.operation, status, (), authorized
        )

    def _prune_expired_contracts(
        self, contracts: dict[str, ObjectDict], now: int
    ) -> None:
        cutoff = now - self._TTL_SECONDS
        expired: list[str] = []
        for key, entry in contracts.items():
            timestamp = entry.get("timestamp")
            if not isinstance(timestamp, int) or timestamp < cutoff:
                expired.append(key)
        for key in expired:
            _ = contracts.pop(key, None)

    def record_first_write_contract(
        self, draft: FirstWriteContractDraft
    ) -> FirstWriteContractRecord:
        timestamp = int(time())
        operation = normalize_contract_operation(draft.operation)
        key = self._contract_key(draft.session_id, draft.target)
        with self._locked_state():
            state = self._load_state()
            self._prune_expired_contracts(state["first_write_contracts"], timestamp)
            state["first_write_contracts"][key] = {
                "schema_version": FIRST_WRITE_CONTRACT_SCHEMA_VERSION,
                "timestamp": timestamp,
                "target": draft.target,
                "operation": operation,
                "reuse_convention": draft.reuse_convention.strip(),
                "stable_behavior_api": draft.stable_behavior_api.strip(),
                "predicted_risks": [risk.strip() for risk in draft.predicted_risks],
                "design_response": draft.design_response.strip(),
                "focused_verification": draft.focused_verification.strip(),
            }
            self._save_state(state)
        return FirstWriteContractRecord(
            draft.target, operation, timestamp, FIRST_WRITE_CONTRACT_SCHEMA_VERSION
        )

    def authorize_first_write_contracts(
        self, session_id: str, targets: list[str], operation: str
    ) -> list[FirstWriteContractCheck]:
        normalized_operation = normalize_contract_operation(operation)
        now = int(time())
        with self._locked_state():
            state = self._load_state()
            contracts = state["first_write_contracts"]
            checks = [
                self._check_entry(
                    contracts.get(self._contract_key(session_id, target)),
                    _ContractIdentity(target, normalized_operation, now),
                )
                for target in targets
            ]
            self._prune_expired_contracts(contracts, now)
            for target, check in zip(targets, checks, strict=True):
                if check.status in _INVALID_STATUSES:
                    _ = contracts.pop(self._contract_key(session_id, target), None)
            if checks and all(check.complete for check in checks):
                for target in targets:
                    key = self._contract_key(session_id, target)
                    entry = object_dict(contracts[key])
                    entry["authorized_at"] = now
                    contracts[key] = entry
            state["first_write_contracts"] = contracts
            self._save_state(state)
        return checks

    def finalize_first_write_contracts(
        self, session_id: str, targets: list[str], operation: str
    ) -> None:
        _ = normalize_contract_operation(operation)
        with self._locked_state():
            state = self._load_state()
            contracts = state["first_write_contracts"]
            for target in targets:
                _ = contracts.pop(self._contract_key(session_id, target), None)
            state["first_write_contracts"] = contracts
            self._save_state(state)
