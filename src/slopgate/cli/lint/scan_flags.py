"""CLI flags for lint analysis subcommands."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from slopgate.constants import (
    LINT_ENV_CLI,
    LINT_ENV_FULL,
    LINT_ENV_NO_INDEX,
    LINT_ENV_PROFILE,
    LINT_ENV_TRUE,
)


@dataclass(frozen=True, slots=True)
class LintScanFlags:
    """CLI flags shared by lint check, strict, and test-integrity."""

    details: bool = False
    profile: bool = False
    full: bool = False
    no_index: bool = False


def scan_flags_from_args(args: argparse.Namespace) -> LintScanFlags:
    """Read lint analysis flags from argparse, defaulting missing attributes."""
    return LintScanFlags(
        details=_flag(args, "details"),
        profile=_flag(args, "profile"),
        full=_flag(args, "full"),
        no_index=_flag(args, "no_index"),
    )


def apply_lint_scan_env(flags: LintScanFlags) -> dict[str, str | None]:
    """Set ``SLOPGATE_LINT_*`` for this CLI scan and return prior values."""
    prior = {
        LINT_ENV_CLI: os.environ.get(LINT_ENV_CLI),
        LINT_ENV_PROFILE: os.environ.get(LINT_ENV_PROFILE),
        LINT_ENV_FULL: os.environ.get(LINT_ENV_FULL),
        LINT_ENV_NO_INDEX: os.environ.get(LINT_ENV_NO_INDEX),
    }
    os.environ[LINT_ENV_CLI] = LINT_ENV_TRUE
    _assign_flag_env(LINT_ENV_PROFILE, flags.profile)
    _assign_flag_env(LINT_ENV_FULL, flags.full)
    _assign_flag_env(LINT_ENV_NO_INDEX, flags.no_index)
    return prior


def restore_lint_scan_env(prior: dict[str, str | None]) -> None:
    """Restore ``SLOPGATE_LINT_*`` values captured by ``apply_lint_scan_env``."""
    for key, value in prior.items():
        if value is None:
            os.environ.pop(key, None)
            continue
        os.environ[key] = value


def _flag(args: argparse.Namespace, name: str) -> bool:
    raw = getattr(args, name, False)
    return raw if isinstance(raw, bool) else False


def _assign_flag_env(key: str, enabled: bool) -> None:
    if enabled:
        os.environ[key] = LINT_ENV_TRUE
        return
    os.environ.pop(key, None)
