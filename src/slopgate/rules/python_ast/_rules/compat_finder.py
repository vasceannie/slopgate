"""Re-export the package-level private-name import hook."""

from slopgate.boot_aliases import PrivateNameFinder, install_private_name_finder

__all__ = ["PrivateNameFinder", "install_private_name_finder"]
