"""Install/uninstall engine for hosts with a local-marketplace plugin manager."""

from __future__ import annotations

from slopgate.installer.native.marketplace.host import (
    MarketplaceCommands,
    MarketplaceHost,
)
from slopgate.installer.native.marketplace.install import install_marketplace_host
from slopgate.installer.native.marketplace.uninstall import uninstall_marketplace_host

__all__ = [
    "MarketplaceCommands",
    "MarketplaceHost",
    "install_marketplace_host",
    "uninstall_marketplace_host",
]
