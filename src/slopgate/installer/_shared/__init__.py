"""Shared installer helpers."""

from __future__ import annotations

import shutil
import subprocess

from slopgate.constants import METADATA_COMMAND
from slopgate.installer._shared.binary import (
    HOOK_TIMEOUT_LONG,
    HOOK_TIMEOUT_SHORT,
    HOOK_TIMEOUT_STANDARD,
    base_invocation,
    find_binary,
    hook_command,
    shell_command,
)
from slopgate.installer._shared.hooks import (
    _powershell_command_argv,
    coerce_hook_entries,
    command_is_slopgate_hook,
    filter_owned_hook_commands,
    load_existing_json_object,
    merge_owned_hooks,
    prepare_owned_hooks_document,
    merge_owned_hooks_into,
    remove_owned_hooks,
    require_json_object,
)
from slopgate.installer._shared.models import (
    ContainedWrite,
    HooksUninstall,
    InstallAt,
    OwnedHooksWrite,
)
from slopgate.installer._shared.paths import (
    UnsafeInstallPathError,
    contained_scope_root,
    report_contained_install_path,
    require_contained_install_path,
)
from slopgate.installer._shared.writes import (
    backup_existing_file,
    backup_existing_file_and_report,
    print_binary_install_summary,
    remove_file_with_backup,
    uninstall_hooks_file,
    write_contained_json,
    write_contained_text,
    write_json_with_backup,
)
from slopgate.util.platform import is_windows

HOOK_TYPE_COMMAND = METADATA_COMMAND

__all__ = [
    "ContainedWrite",
    "HOOK_TIMEOUT_LONG",
    "HOOK_TIMEOUT_SHORT",
    "HOOK_TIMEOUT_STANDARD",
    "HOOK_TYPE_COMMAND",
    "HooksUninstall",
    "InstallAt",
    "OwnedHooksWrite",
    "UnsafeInstallPathError",
    "backup_existing_file",
    "backup_existing_file_and_report",
    "base_invocation",
    "coerce_hook_entries",
    "command_is_slopgate_hook",
    "contained_scope_root",
    "filter_owned_hook_commands",
    "find_binary",
    "hook_command",
    "is_windows",
    "load_existing_json_object",
    "merge_owned_hooks",
    "prepare_owned_hooks_document",
    "merge_owned_hooks_into",
    "print_binary_install_summary",
    "remove_file_with_backup",
    "remove_owned_hooks",
    "report_contained_install_path",
    "require_contained_install_path",
    "require_json_object",
    "shell_command",
    "shutil",
    "subprocess",
    "uninstall_hooks_file",
    "write_contained_json",
    "write_contained_text",
    "write_json_with_backup",
    "_powershell_command_argv",
]
