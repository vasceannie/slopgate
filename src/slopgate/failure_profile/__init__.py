"""Privacy-safe aggregate repository failure profiles."""

from __future__ import annotations

from ._capture import (
    FailureProfileCapture,
    active_retry_locks,
    capture_failure_profile,
)
from ._models import (
    FailureProfileDimension,
    FailureProfileEntry,
    FailureProfileSnapshot,
    FailureRisk,
)
from ._guidance import FailureProfileGuidance, first_write_profile_guidance
from ._store import FailureProfileStore, PROFILE_SCHEMA_VERSION

__all__ = [
    "FailureProfileCapture",
    "FailureProfileDimension",
    "FailureProfileEntry",
    "FailureProfileGuidance",
    "FailureProfileSnapshot",
    "FailureProfileStore",
    "FailureRisk",
    "PROFILE_SCHEMA_VERSION",
    "active_retry_locks",
    "capture_failure_profile",
    "first_write_profile_guidance",
]
