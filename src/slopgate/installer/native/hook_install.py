"""Shared setup for hosts integrated through local native hooks."""

from __future__ import annotations

from slopgate.installer._install_scope import InstallScope, normalize_install_scope
from slopgate.installer._shared import find_binary

__all__ = ["prepare_native_hooks_install"]


def prepare_native_hooks_install(scope: str) -> tuple[InstallScope, str]:
    """Resolve the requested scope and Slopgate binary for native hooks."""
    install_scope = normalize_install_scope(scope)
    binary = find_binary()
    print("Installation mode: native hooks (not a registered plugin)")
    return install_scope, binary
