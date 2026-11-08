"""Pi-native package installation and prior-extension migration support."""

from slopgate.installer.native.pi.cutover import PiCutover
from slopgate.installer.native.pi.install import install_pi_package
from slopgate.installer.native.pi.legacy import (
    EXTENSION_DIR_NAME,
    EXTENSION_ENTRY_NAME,
    LEGACY_ENTRY_NAME,
    LEGACY_PACKAGE_ENTRY_NAME,
    PI_OWNERSHIP_MARKERS,
    pi_agent_dir,
    pi_extension_has_owned_slopgate,
    pi_project_extension_path,
    pi_user_extension_path,
    render_pi_extension,
)
from slopgate.installer.native.pi.package import (
    PI_PACKAGE_NAME,
    build_pi_plan,
    pi_manifest,
)
from slopgate.installer.native.pi.settings import (
    PackageEntry,
    package_entries,
    project_settings_path,
    registered_entry,
    resolve_source,
    settings_directory,
    settings_path,
    user_settings_path,
)
from slopgate.installer.native.pi.uninstall import uninstall_pi_package

__all__ = [
    "EXTENSION_DIR_NAME",
    "EXTENSION_ENTRY_NAME",
    "LEGACY_ENTRY_NAME",
    "LEGACY_PACKAGE_ENTRY_NAME",
    "PI_OWNERSHIP_MARKERS",
    "PI_PACKAGE_NAME",
    "PackageEntry",
    "PiCutover",
    "build_pi_plan",
    "install_pi_package",
    "package_entries",
    "pi_agent_dir",
    "pi_extension_has_owned_slopgate",
    "pi_manifest",
    "pi_project_extension_path",
    "pi_user_extension_path",
    "registered_entry",
    "render_pi_extension",
    "resolve_source",
    "settings_directory",
    "settings_path",
    "project_settings_path",
    "uninstall_pi_package",
    "user_settings_path",
]
