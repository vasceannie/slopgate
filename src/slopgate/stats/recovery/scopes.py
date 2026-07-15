"""Recovery-report scope selection over normalized events."""

from __future__ import annotations

from enum import Enum
from typing import Final

from slopgate.constants import LINT_SCOPE_ALL

from .records import NormalizedEvent


class RecoveryScope(str, Enum):
    MANAGED = "managed"
    RELAXED = "relaxed"
    GLOBAL = "global"
    ALL = LINT_SCOPE_ALL


RECOVERY_SCOPE_CHOICES: Final = tuple(scope.value for scope in RecoveryScope)

_MODE_BY_SCOPE: Final = {
    RecoveryScope.MANAGED: "repo_strict",
    RecoveryScope.RELAXED: "repo_relaxed",
    RecoveryScope.GLOBAL: "outside_repo",
}


def scoped_events(
    events: tuple[NormalizedEvent, ...], scope: RecoveryScope
) -> tuple[NormalizedEvent, ...]:
    """Select one non-blended recovery scope from normalized events."""
    if scope is RecoveryScope.ALL:
        return events
    mode = _MODE_BY_SCOPE[scope]
    return tuple(event for event in events if event.enforcement_mode == mode)
