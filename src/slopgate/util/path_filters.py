from __future__ import annotations

# Paths containing any of these directory names are third-party, generated,
# or virtual-environment code and should be excluded from author-owned quality
# enforcement while still remaining readable for inspection/debugging.
THIRD_PARTY_DIR_NAMES = frozenset(
    {
        ".venv",
        ".venvs",
        "venv",
        "env",
        "site-packages",
        "node_modules",
        ".tox",
        ".nox",
        ".eggs",
    }
)


def is_third_party_or_virtualenv_path(path_value: str) -> bool:
    """Return True when *path_value* points at third-party or virtualenv code."""
    normalized = path_value.replace("\\", "/")
    return any(part in THIRD_PARTY_DIR_NAMES for part in normalized.split("/"))


def is_authored_python_path(path_value: str) -> bool:
    """Return True when *path_value* is project-authored Python source."""
    return path_value.lower().endswith(
        (".py", ".pyi")
    ) and not is_third_party_or_virtualenv_path(path_value)
