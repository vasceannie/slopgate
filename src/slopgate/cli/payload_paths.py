"""Make WSL-style paths in a hook payload resolvable by Slopgate on Windows.

A Claude Code running inside WSL invokes the Windows Slopgate through
``powershell.exe`` and reports files as Linux paths. Windows Python would read
drive mounts as ``C:\\mnt\\c\\...`` and home paths as paths on the current
drive, miss every repository and file, and let each edit through.

Such a payload is recognized by ``WSL_DISTRO_NAME``, which Windows processes
only see when a WSL caller forwards it through ``WSLENV``, as the installed
WSL hook command does. Hosts running natively on Windows never forward it, so
their payloads (including Git Bash style ``/c/...`` paths) are left as sent.

For a WSL payload, the sending distribution translates every Linux path field
itself in one call, as the user the hook command forwards (``SLOPGATE_WSL_USER``):
``realpath -m`` resolves symlinks and ``..`` exactly as they resolve for the
tool (textual rewriting cannot know that ``link/../x`` lands on another drive
when ``link`` points into a drive mount, and another user without the
sender's directory permissions silently stops following symlinks), and
``wslpath -w`` maps the result through that distribution's own mounts, custom
automount roots included, to a drive path or a ``\\\\wsl.localhost\\...`` UNC
path. When the user is not forwarded, or the distribution cannot answer, the
payload is refused rather than mapped from guesses.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Iterator
from typing import cast

from slopgate._types import ObjectDict
from slopgate.constants import (
    METADATA_CWD,
    METADATA_PATH,
    REPLACE,
    WSL_DISTRO_ENV,
    WSL_USER_ENV,
)
from slopgate.util import logger
from slopgate.util.platform import child_creation_flags, is_windows

__all__ = ["UnmappedWslPathError", "payload_with_windows_paths"]

_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:\\|\\\\[^\\])")
# Positional arguments are the Linux paths; each answer is NUL-terminated.
# ``&& printf x`` keeps command substitution from eating trailing newlines
# that belong to a file name; ``%?x`` then drops exactly the added "\nx".
_TRANSLATE_SCRIPT = (
    "for path do "
    'real=$(realpath -m -- "$path" && printf x) || exit 1; '
    'windows=$(wslpath -w "${real%?x}" && printf x) || exit 1; '
    "printf '%s\\000' \"${windows%?x}\"; "
    "done"
)
_TRANSLATE_TIMEOUT_SECONDS = 10
_NUL = "\0"
_PATH_KEYS = frozenset(
    {
        METADATA_CWD,
        "file_path",
        "filePath",
        "notebook_path",
        METADATA_PATH,
        "project_dir",
        "transcript_path",
        "worktree",
    }
)
_PathMapper = Callable[[str], str]


class UnmappedWslPathError(ValueError):
    """A payload path cannot be located in the WSL distribution that sent it."""


def payload_with_windows_paths(payload: ObjectDict) -> ObjectDict:
    """``payload`` with WSL paths rewritten for Windows; unchanged elsewhere.

    Only a payload from a forwarded WSL distribution (``WSL_DISTRO_NAME``) is
    rewritten, as the user that sent it (``SLOPGATE_WSL_USER``). Raises
    ``UnmappedWslPathError`` when that user is not forwarded or the
    distribution cannot translate the Linux path fields.
    """
    if not is_windows():
        return payload
    distro = os.environ.get(WSL_DISTRO_ENV, "")
    if not distro:
        return payload
    linux_paths = list(dict.fromkeys(_linux_path_fields(payload, "")))
    if not linux_paths:
        return payload
    user = os.environ.get(WSL_USER_ENV, "")
    if not user:
        # Another user (the distribution default) may lack the sender's
        # directory permissions; realpath -m then silently stops following
        # symlinks, so its answer cannot stand in for the sender's.
        raise UnmappedWslPathError(
            f"hook payload came from WSL distribution {distro} without "
            f"{WSL_USER_ENV}, so its paths cannot be resolved as the user that "
            "sent them; reinstall the Slopgate hooks (slopgate install) so the "
            "hook command forwards it"
        )
    windows_paths = _translated_paths(distro, user, linux_paths)
    return cast(ObjectDict, _rewrite(payload, "", windows_paths.__getitem__))


def _linux_path_fields(value: object, key: str) -> Iterator[str]:
    """Every Linux path in a path field of ``value``, in payload order."""
    if isinstance(value, dict):
        for name, item in cast(dict[str, object], value).items():
            yield from _linux_path_fields(item, name)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            yield from _linux_path_fields(item, key)
    elif isinstance(value, str) and key in _PATH_KEYS and value.startswith("/"):
        yield value


def _translated_paths(distro: str, user: str, paths: list[str]) -> dict[str, str]:
    """Each path as ``user`` in ``distro`` resolves and maps it, or refuse."""
    answer = _wsl_translate(distro, user, paths)
    if isinstance(answer, str):
        logger.warning(
            "hook payload WSL translation failed", distro=distro, error=answer
        )
        raise UnmappedWslPathError(
            f"WSL distribution {distro} could not translate the hook payload "
            f"paths (realpath -m, wslpath -w): {answer}"
        )
    return dict(zip(paths, answer, strict=True))


def _wsl_translate(distro: str, user: str, paths: list[str]) -> list[str] | str:
    """Windows paths for ``paths`` from one ``wsl`` call, or why it failed."""
    command = ["wsl", "-d", distro, "-u", user, "-e", "sh", "-c", _TRANSLATE_SCRIPT]
    try:
        completed = subprocess.run(
            [*command, "sh", *paths],
            capture_output=True,
            timeout=_TRANSLATE_TIMEOUT_SECONDS,
            creationflags=child_creation_flags(),
            check=False,
        )
    # ValueError: an argument no process can receive (an embedded NUL, an
    # unencodable character); refusing it keeps a decoy field from turning
    # the hook into a non-blocking crash.
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return str(exc)
    try:
        output = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        return str(exc)
    # Exactly one NUL-terminated absolute Windows path per input; anything
    # else (trailing noise, a missing terminator, a short answer) is no answer.
    translated = output.split(_NUL)[:-1]
    framed = output.endswith(_NUL) and len(translated) == len(paths)
    if (
        completed.returncode != 0
        or not framed
        or not all(_WINDOWS_ABSOLUTE.match(path) for path in translated)
    ):
        detail = completed.stderr.decode("utf-8", errors=REPLACE).strip()
        return detail or f"exit {completed.returncode}: malformed translation output"
    return translated


def _rewrite(value: object, key: str, mapper: _PathMapper) -> object:
    if isinstance(value, dict):
        items = cast(dict[str, object], value)
        return {name: _rewrite(item, name, mapper) for name, item in items.items()}
    if isinstance(value, list):
        return [_rewrite(item, key, mapper) for item in cast(list[object], value)]
    if isinstance(value, str) and key in _PATH_KEYS and value.startswith("/"):
        return mapper(value)
    return value
