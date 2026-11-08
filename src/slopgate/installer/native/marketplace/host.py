"""Host contracts for local-marketplace plugin managers (OMP, Claude)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from slopgate.installer.native.model import LegacyCutover, NativeRequest, Registration
from slopgate.installer.native.packages import MARKETPLACE_NAME, PackagePlan
from slopgate.installer.native.settings_guard import NativeSettingsFile

__all__ = ["MarketplaceCommands", "MarketplaceHost"]


class MarketplaceCommands(ABC):
    """Argument arrays for a host's native plugin-manager mutations."""

    @abstractmethod
    def marketplace_add(self, entry_root: Path) -> list[str]:
        """Register the staged local marketplace."""

    @abstractmethod
    def marketplace_update(self) -> list[str]:
        """Refresh the cached marketplace catalog from its source."""

    @abstractmethod
    def marketplace_remove(self) -> list[str]:
        """Forget the staged local marketplace."""

    @abstractmethod
    def install(self, scope: str, previous: Registration | None) -> list[list[str]]:
        """Register the plugin, restoring ``previous`` native state when given."""

    @abstractmethod
    def replace(self, scope: str, previous: Registration) -> list[list[str]]:
        """Replace an existing registration while keeping its native state."""

    @abstractmethod
    def uninstall(self, scope: str) -> list[str]:
        """Remove one scope's registration."""


class MarketplaceHost(ABC):
    """Identity, staging, inventory and prior-install handling for one host."""

    platform: str
    label: str
    executable: str
    plugin_name: str
    list_command: str
    activation_note: str
    commands: MarketplaceCommands

    @property
    def plugin_id(self) -> str:
        return f"{self.plugin_name}@{MARKETPLACE_NAME}"

    @abstractmethod
    def build_plan(self, binary: str) -> PackagePlan:
        """Plan the staged marketplace for the resolved Slopgate binary."""

    @abstractmethod
    def legacy_cutover(self, request: NativeRequest) -> LegacyCutover:
        """Create the scope-bound migration for one request."""

    @abstractmethod
    def marketplace_sources(self, cwd: Path) -> dict[str, str]:
        """Return configured marketplace name -> source as the host reports it."""

    @abstractmethod
    def registrations(self, cwd: Path) -> list[Registration]:
        """Return this plugin's native registrations visible from ``cwd``."""

    def project_anchor_issue(self, root: Path) -> str | None:
        """Return why native project scope would not target ``root``, if so."""
        _ = root
        return None

    def project_anchor_action(self, root: Path) -> str | None:
        """Describe a project anchor created by a real install, if needed."""
        _ = root
        return None

    def ensure_project_anchor(self, root: Path) -> Path | None:
        """Create a missing project anchor; return the created path for rollback."""
        _ = root
        return None

    def native_settings(self, scope: str, root: Path) -> tuple[NativeSettingsFile, ...]:
        """List host-owned settings files a registration in ``scope`` rewrites."""
        _ = (scope, root)
        return ()
