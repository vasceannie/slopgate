"""Engine integration for aggregate failure-profile capture."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from slopgate._types import ObjectDict, string_value
from slopgate.config import resolve_repo_root
from slopgate.constants import (
    BLOCK,
    DENY,
    LANGUAGE_BY_SUFFIX,
    METADATA_PATH,
    METADATA_RULE_ID,
    PYTEST_TEST_PREFIX,
    UNKNOWN_VALUE,
)
from slopgate.context import HookContext
from slopgate.models import RuleFinding
from slopgate.util.metadata_paths import effective_metadata_path

from ._models import FailureProfileDimension
from ._store import FailureProfileStore


EnforcementMode = Literal["outside_repo", "repo_strict", "repo_relaxed"]
_LANGUAGE_BY_SUFFIX: Final = {
    **LANGUAGE_BY_SUFFIX,
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}
_CONFIG_SUFFIXES: Final = {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}
_META_RULE_IDS: Final = {
    "RETRY-BUDGET-001",
    "WORKFLOW-FIRST-WRITE-001",
}


@dataclass(frozen=True, slots=True)
class _FailureProfileCapture:
    platform: str
    model_identifier: str | None
    enforcement_mode: EnforcementMode
    findings: tuple[RuleFinding, ...]
    prior_retry_locks: dict[str, ObjectDict]


def _active_retry_locks(ctx: HookContext) -> dict[str, ObjectDict]:
    repo_root = (resolve_repo_root(ctx.cwd) or ctx.cwd).resolve(strict=False)
    return ctx.state.active_semantic_retry_locks(ctx.session_id, str(repo_root))


def _capture_failure_profile(ctx: HookContext, capture: _FailureProfileCapture) -> None:
    if (
        capture.enforcement_mode != "repo_strict"
        or not ctx.config.failure_profile.enabled
    ):
        return
    store = FailureProfileStore(
        ctx.config.trace_dir, ctx.config.repo_root, ctx.config.failure_profile
    )
    for finding in capture.findings:
        if finding.decision not in {BLOCK, DENY} or finding.rule_id in _META_RULE_IDS:
            continue
        path_value = effective_metadata_path(finding.metadata)
        store.record(
            FailureProfileDimension(
                finding.rule_id,
                _path_role(path_value),
                _language(ctx, path_value),
                capture.platform,
                capture.model_identifier,
                "blocked",
            )
        )
    active_keys = set(_active_retry_locks(ctx))
    for raw_key, lock in capture.prior_retry_locks.items():
        if raw_key in active_keys:
            continue
        rule_id = string_value(lock.get(METADATA_RULE_ID))
        if not rule_id:
            continue
        path_value = string_value(lock.get(METADATA_PATH)) or None
        store.record(
            FailureProfileDimension(
                rule_id,
                _path_role(path_value),
                _language(ctx, path_value),
                capture.platform,
                capture.model_identifier,
                "resolved",
            )
        )


def _path_role(path_value: str | None) -> str:
    if not path_value:
        return "pathless"
    path = Path(path_value)
    normalized = path.as_posix().casefold()
    if "/tests/" in f"/{normalized}" or path.name.casefold().startswith(
        PYTEST_TEST_PREFIX
    ):
        return "test"
    if "/docs/" in f"/{normalized}" or path.suffix.casefold() in {".md", ".rst"}:
        return "documentation"
    if path.suffix.casefold() in _CONFIG_SUFFIXES or path.name.startswith("."):
        return "configuration"
    return "source"


def _language(ctx: HookContext, path_value: str | None) -> str:
    if path_value:
        language = _LANGUAGE_BY_SUFFIX.get(Path(path_value).suffix.casefold())
        if language is not None:
            return language
    return next(iter(sorted(ctx.languages)), UNKNOWN_VALUE)


FailureProfileCapture, active_retry_locks, capture_failure_profile = (
    _FailureProfileCapture,
    _active_retry_locks,
    _capture_failure_profile,
)
