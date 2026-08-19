"""Group flat sibling filenames and format the suggested package layout."""

from __future__ import annotations

from pathlib import Path

from slopgate.util.path_filters import PYTHON_SOURCE_SUFFIXES

from .paths import prefix_for_name

_PY_SUFFIX, _PYI_SUFFIX = PYTHON_SOURCE_SUFFIXES


def prefix_groups(
    directory: Path, extra_files: set[str], removed_files: set[str]
) -> dict[str, list[str]]:
    """Group existing plus projected sibling files by shared package prefix."""
    groups: dict[str, list[str]] = {}
    names = set(extra_files)
    if directory.exists():
        for child in directory.iterdir():
            if child.is_file():
                names.add(child.name)
    names.difference_update(removed_files)
    for name in names:
        prefix = prefix_for_name(name)
        if prefix is not None:
            groups.setdefault(prefix, []).append(name)
    return groups


def module_name_for_package(files: list[str], prefix: str) -> list[str]:
    """Return suggested child-module names for a prefix_* sibling group."""
    modules: list[str] = []
    for name in sorted(files)[:5]:
        stem = name.removesuffix(_PYI_SUFFIX).removesuffix(_PY_SUFFIX)
        for tag in (f"_{prefix}_", f"{prefix}_"):
            if stem.startswith(tag):
                stem = stem.removeprefix(tag)
                break
        modules.append(f"{stem}{_PY_SUFFIX}")
    return modules


def build_pkg_block(files: list[str], prefix: str) -> str:
    """Return indented child-module lines for the suggested package layout."""
    return "\n".join(
        ("        " + module for module in module_name_for_package(files, prefix))
    )


def has_same_named_package(parent: Path, prefix: str) -> bool:
    """Return True when parent already contains prefix/__init__.py."""
    package = parent / prefix
    return package.is_dir() and (package / "__init__.py").exists()


def sibling_group_message(parent_name: str, prefix: str, files_str: str, reason: str) -> str:
    """Return the PY-CODE-017 finding message for one sibling group."""
    nl = "\n"
    return (
        f"Directory `{parent_name}/` has flat `{prefix}_*.py` sibling modules "
        f"({files_str}); {reason}. Convert to a sub-package instead:{nl}{nl}"
        f"    {parent_name}/{prefix}/{nl}"
        f"        __init__.py   (re-export public API)"
    )
