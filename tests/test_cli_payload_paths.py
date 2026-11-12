"""WSL paths in hook payloads must resolve on a Windows Slopgate."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, strategies

from slopgate.cli.payload_paths import UnmappedWslPathError, payload_with_windows_paths
from tests.native.wsl_support import install_wsl_commands, install_wsl_script

_IS_WINDOWS = "slopgate.cli.payload_paths.is_windows"
_DISTRO_ENV = "WSL_DISTRO_NAME"
_USER_ENV = "SLOPGATE_WSL_USER"


def _windows_with_distro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, distro: str = "Ubuntu"
) -> Path:
    """Pretend to be Windows called by ``ops`` in ``distro``; return its "/"."""
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.setenv(_DISTRO_ENV, distro)
    monkeypatch.setenv(_USER_ENV, "ops")
    install_wsl_commands(tmp_path, monkeypatch)
    distro_root = tmp_path / "distro-fs"
    distro_root.mkdir()
    monkeypatch.setenv("FAKE_WSL_FS", str(distro_root))
    return distro_root


def test_payload_paths_are_rewritten_on_windows_without_touching_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows_with_distro(tmp_path, monkeypatch)
    payload: dict[str, object] = {
        "cwd": "/mnt/c/Users/PC/repo",
        "transcript_path": "/home/trav/.claude/projects/t.jsonl",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/home/trav/repo/src/a.py",
            "content": "/home/not/a/path/field",
            "edits": [{"path": "/mnt/d/x.py"}],
        },
    }

    rewritten = payload_with_windows_paths(payload)

    assert rewritten == {
        "cwd": "C:\\Users\\PC\\repo",
        "transcript_path": "\\\\wsl.localhost\\Ubuntu\\home\\trav\\.claude\\projects\\t.jsonl",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "\\\\wsl.localhost\\Ubuntu\\home\\trav\\repo\\src\\a.py",
            "content": "/home/not/a/path/field",
            "edits": [{"path": "D:\\x.py"}],
        },
    }, "path fields become drive or WSL UNC paths; file content is left alone"


def test_linux_path_traversal_maps_to_the_directory_wsl_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows_with_distro(tmp_path, monkeypatch)

    rewritten = payload_with_windows_paths(
        {"cwd": "/home/trav/repo/../other", "file_path": "/mnt/c/repo/../../d/x.py"}
    )

    assert rewritten == {
        "cwd": "\\\\wsl.localhost\\Ubuntu\\home\\trav\\other",
        "file_path": "D:\\x.py",
    }, "the engine must see the file WSL edits, never a textual rewrite of '..'"


def test_symlinks_are_followed_inside_the_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distro_root = _windows_with_distro(tmp_path, monkeypatch)
    (distro_root / "mnt" / "d" / "proj").mkdir(parents=True)
    (distro_root / "home" / "trav").mkdir(parents=True)
    (distro_root / "home" / "trav" / "link").symlink_to(distro_root / "mnt/d/proj")

    rewritten = payload_with_windows_paths(
        {"cwd": "/home/trav/link/sub", "file_path": "/home/trav/link/../x.py"}
    )

    assert rewritten == {"cwd": "D:\\proj\\sub", "file_path": "D:\\x.py"}, (
        "a symlink into a drive mount, and a '..' after it, must land where the "
        "kernel resolves them, not where the text points"
    )


def test_all_payload_paths_translate_in_one_call_as_the_forwarded_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows_with_distro(tmp_path, monkeypatch, distro="Debian")
    log = tmp_path / "wsl.log"
    monkeypatch.setenv("FAKE_WSL_LOG", str(log))

    _ = payload_with_windows_paths(
        {"cwd": "/home/trav/repo", "tool_input": {"file_path": "/mnt/c/x.py"}}
    )

    assert log.read_text(encoding="utf-8").splitlines() == [
        "Debian ops -e sh -c <script> sh /home/trav/repo /mnt/c/x.py"
    ], (
        "one translation call, as the sending user in its distribution, covers every path"
    )


@dataclass(frozen=True, slots=True)
class _SenderCase:
    user: str
    """Forwarded ``SLOPGATE_WSL_USER``; empty when the hook did not forward it."""
    payload: dict[str, object]
    reason: str


_SENDER_CASES = (
    _SenderCase("", {"cwd": "/mnt/c/Users/PC/repo"}, f"without {_USER_ENV}"),
    _SenderCase(
        "ops",
        {"cwd": "/mnt/c/repo", "tool_input": {"file_path": "/mnt/c/a\0b"}},
        "could not translate",
    ),
)


@pytest.mark.parametrize(
    "case", _SENDER_CASES, ids=("user-not-forwarded", "nul-in-decoy-path")
)
def test_payload_that_cannot_be_resolved_as_its_sender_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: _SenderCase
) -> None:
    _windows_with_distro(tmp_path, monkeypatch)
    monkeypatch.setenv(_USER_ENV, case.user)

    with pytest.raises(UnmappedWslPathError, match=case.reason):
        payload_with_windows_paths(case.payload)


def test_drives_under_a_custom_automount_root_keep_their_drive_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows_with_distro(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_WSL_AUTOMOUNT", "/")

    rewritten = payload_with_windows_paths(
        {"cwd": "/c/Users/PC/repo", "file_path": "/mnt/c/x.py"}
    )

    assert rewritten == {
        "cwd": "C:\\Users\\PC\\repo",
        "file_path": "\\\\wsl.localhost\\Ubuntu\\mnt\\c\\x.py",
    }, "the distribution's own mounts decide which paths are drives, not '/mnt/'"


def test_native_windows_posix_paths_are_left_as_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.delenv(_DISTRO_ENV, raising=False)
    install_wsl_script(tmp_path, monkeypatch, "raise SystemExit(3)\n")
    payload: dict[str, object] = {
        "cwd": "/c/Users/PC/repo",
        "tool_input": {"file_path": "/c/Users/PC/repo/a.py"},
    }

    assert payload_with_windows_paths(payload) is payload, (
        "without a forwarded WSL distribution the host runs natively on Windows "
        "(Git Bash style paths included): nothing to translate or refuse"
    )


_STDOUT = "import sys\nsys.stdout.write({!r})\n"
_UNUSABLE_WSL_ANSWERS = {
    "nonzero-exit": "raise SystemExit(3)\n",
    "trailing-noise": _STDOUT.format("C:\\Users\\PC\\repo\0junk"),
    "no-terminator": _STDOUT.format("C:\\Users\\PC\\repo"),
    "linux-answer": _STDOUT.format("/mnt/c/Users/PC/repo\0"),
    "relative-answer": _STDOUT.format("Users\\PC\\repo\0"),
    "extra-record": _STDOUT.format("C:\\a\0C:\\b\0"),
    "partial-then-fail": _STDOUT.format("C:\\a\0") + "raise SystemExit(1)\n",
}


def _windows_with_answering_wsl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wsl_body: str
) -> None:
    """Pretend to be Windows called from Ubuntu, whose ``wsl`` runs ``wsl_body``."""
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.setenv(_DISTRO_ENV, "Ubuntu")
    monkeypatch.setenv(_USER_ENV, "ops")
    install_wsl_script(tmp_path, monkeypatch, wsl_body)


@pytest.mark.parametrize(
    "wsl_body", tuple(_UNUSABLE_WSL_ANSWERS.values()), ids=tuple(_UNUSABLE_WSL_ANSWERS)
)
def test_distribution_that_cannot_resolve_paths_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wsl_body: str
) -> None:
    _windows_with_answering_wsl(tmp_path, monkeypatch, wsl_body)

    with pytest.raises(UnmappedWslPathError, match="Ubuntu could not translate"):
        payload_with_windows_paths({"cwd": "/mnt/c/Users/PC/repo"})


def test_windows_only_payload_needs_no_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.delenv(_DISTRO_ENV, raising=False)
    payload: dict[str, object] = {
        "cwd": "C:\\repo",
        "tool_input": {"file_path": "C:\\x.py"},
    }

    assert payload_with_windows_paths(payload) is payload, (
        "a native Windows Claude sends Windows paths; nothing to resolve or refuse"
    )


@dataclass(frozen=True, slots=True)
class _Origin:
    windows: bool
    distro: str
    user: str
    """Empty ``distro``/``user``: not forwarded."""


def _outcome(origin: _Origin, payload: dict[str, object]) -> str:
    """What the rewrite does with ``payload``; no ``wsl`` exists to answer."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_IS_WINDOWS, lambda: origin.windows)
        patch.setenv("PATH", os.path.join(os.sep, "nonexistent-wsl-bin"))
        patch.setenv(_DISTRO_ENV, origin.distro)
        patch.setenv(_USER_ENV, origin.user)
        try:
            result = payload_with_windows_paths(payload)
        except UnmappedWslPathError as exc:
            return "refuse-user" if _USER_ENV in str(exc) else "refuse-translate"
    return "unchanged" if result is payload else "rewritten"


_FIELD_VALUE = strategies.one_of(
    strategies.from_regex(r"\A/[a-z./]{0,12}\Z"),
    strategies.from_regex(r"\A[A-Z]:\\[a-z\\]{0,8}\Z"),
    strategies.text(max_size=8).filter(lambda value: not value.startswith("/")),
)


_ORIGINS = strategies.builds(
    _Origin,
    windows=strategies.booleans(),
    distro=strategies.sampled_from(("", "Ubuntu")),
    user=strategies.sampled_from(("", "ops")),
)
_FIELDS = strategies.dictionaries(
    strategies.sampled_from(("cwd", "file_path", "transcript_path", "content")),
    _FIELD_VALUE,
    max_size=4,
)
# (WSL payload with a Linux path field, user forwarded) -> outcome.
_EXPECTED_OUTCOME = {
    (False, False): "unchanged",
    (False, True): "unchanged",
    (True, False): "refuse-user",
    (True, True): "refuse-translate",
}


def _expected_outcome(origin: _Origin, fields: dict[str, str]) -> str:
    linux = any(key != "content" and value[:1] == "/" for key, value in fields.items())
    wsl_payload = origin.windows and bool(origin.distro) and linux
    return _EXPECTED_OUTCOME[(wsl_payload, bool(origin.user))]


@given(origin=_ORIGINS, fields=_FIELDS)
def test_only_forwarded_wsl_payloads_with_linux_paths_reach_wsl_property(
    origin: _Origin, fields: dict[str, str]
) -> None:
    assert _outcome(origin, dict(fields)) == _expected_outcome(origin, fields), (
        "native or path-free payloads pass untouched; a WSL payload without its "
        "user is refused before wsl runs, and with it only wsl's answer counts"
    )
