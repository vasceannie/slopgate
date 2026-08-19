"""Options for lint collector runners."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate.lint._helpers.profile import LintProfile
from slopgate.lint.catalog import CatalogSurface


@dataclass(frozen=True, slots=True)
class CollectorRunOptions:
    """Surface, indexing, and integrity mode for one collector run."""

    surface: CatalogSurface = "cli"
    event: str | None = None
    build_constants: bool = True
    integrity_mode: str = "full"
    profile: LintProfile | None = None
    persist_index: bool = False
    use_index: bool = True
    rebuild_index: bool = False


def collector_options_from_env() -> CollectorRunOptions:
    """Build collector run options from ``SLOPGATE_LINT_*`` environment flags."""
    import os

    from slopgate.constants import (
        LINT_ENV_CLI,
        LINT_ENV_FULL,
        LINT_ENV_NO_INDEX,
        LINT_ENV_PROFILE,
        LINT_ENV_TRUE,
    )

    cli_mode = os.environ.get(LINT_ENV_CLI) == LINT_ENV_TRUE
    profile_on = os.environ.get(LINT_ENV_PROFILE) == LINT_ENV_TRUE
    no_index = os.environ.get(LINT_ENV_NO_INDEX) == LINT_ENV_TRUE
    return CollectorRunOptions(
        profile=LintProfile() if profile_on else None,
        persist_index=cli_mode and not no_index,
        use_index=not no_index,
        rebuild_index=os.environ.get(LINT_ENV_FULL) == LINT_ENV_TRUE,
    )
