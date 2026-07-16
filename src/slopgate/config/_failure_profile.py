"""Per-repository aggregate failure-profile configuration."""

from __future__ import annotations

from slopgate.models import FailureProfileConfig
from slopgate.policy_defaults import (
    FAILURE_PROFILE_MAX_ENTRIES,
    FAILURE_PROFILE_RETENTION_DAYS,
)

from ._coerce import bool_value, int_value, object_dict


def failure_profile_config(toml_data: dict[str, object]) -> FailureProfileConfig:
    section = object_dict(toml_data.get("failure_profile", {}))
    return FailureProfileConfig(
        enabled=bool_value(section.get("enabled"), False),
        retention_days=max(
            1,
            int_value(section.get("retention_days"), FAILURE_PROFILE_RETENTION_DAYS),
        ),
        max_entries=max(
            1, int_value(section.get("max_entries"), FAILURE_PROFILE_MAX_ENTRIES)
        ),
    )
