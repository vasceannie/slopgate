"""Canonical user and project config paths for native hosts."""

from __future__ import annotations

from pathlib import Path


def user_host_root(host: str) -> Path:
    """Return a host's existing home-directory config root."""
    return Path.home() / f".{host}"


def user_host_file(host: str, filename: str) -> Path:
    """Return a host config file in its home-directory root."""
    return user_host_root(host) / filename


def project_host_file(host: str, filename: str, root: Path) -> Path:
    """Return a host config file beneath the selected project root."""
    return root / f".{host}" / filename
