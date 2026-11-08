"""Shared value types and contracts for native harness registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer._install_scope import (
    normalize_install_scope,
    resolve_project_root,
)

HOOKS_KEY = "hooks"
SOURCE_KEY = "source"
VERSION_KEY = "version"


__all__ = [
    "HOOKS_KEY",
    "LegacyCutover",
    "LegacyRefusal",
    "NativeRequest",
    "Registration",
    "SOURCE_KEY",
    "VERSION_KEY",
    "expand_scopes",
    "make_request",
    "make_request_or_report",
]


class LegacyRefusal(RuntimeError):
    """Prior artifacts cannot be safely recognized or modified."""


@dataclass(frozen=True, slots=True)
class Registration:
    """One native registration as reported by the host's own inventory."""

    identity: str
    scope: str
    version: str | None
    enabled: bool | None
    project: Path | None = None


@dataclass(frozen=True, slots=True)
class NativeRequest:
    """A validated install/uninstall request expanded into explicit scopes."""

    dry_run: bool
    scopes: tuple[str, ...]
    root: Path


def expand_scopes(scope: str) -> tuple[str, ...]:
    """Expand ``both`` into explicit ordered scopes; native CLIs never see it."""
    normalized = normalize_install_scope(scope)
    if normalized == INSTALL_SCOPE_BOTH:
        return (INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT)
    return (normalized,)


def make_request(
    scope: str, project_root: Path | None, *, dry_run: bool
) -> NativeRequest:
    """Normalize scope/root input; raises ``ValueError`` for an invalid scope."""
    return NativeRequest(
        dry_run=dry_run,
        scopes=expand_scopes(scope),
        root=resolve_project_root(project_root),
    )


def make_request_or_report(
    scope: str, project_root: Path | None, dry_run: bool
) -> NativeRequest | None:
    """Build a native request, printing validation errors for CLI callers."""
    try:
        return make_request(scope, project_root, dry_run=dry_run)
    except ValueError as exc:
        print(str(exc))
        return None


class LegacyCutover(ABC):
    """Scope-aware discovery, removal and rollback of pre-native enforcement."""

    @abstractmethod
    def preflight(self) -> None:
        """Validate every requested scope; raise the refusal error on any problem."""

    @abstractmethod
    def describe(self) -> list[str]:
        """Return human-readable actions for dry-run output (read-only)."""

    @abstractmethod
    def capture(self) -> None:
        """Record the state needed to restore previously installed artifacts."""

    @abstractmethod
    def remove(self, scope: str) -> int:
        """Retire prior enforcement for one scope; return a process status."""

    @abstractmethod
    def restore(self) -> int:
        """Undo every ``remove`` since ``capture``; return 1 when incomplete.

        Must be a no-op when ``capture`` or ``remove`` never ran.
        """
