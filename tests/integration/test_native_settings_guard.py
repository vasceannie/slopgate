"""Native settings guards restore what a host registration command rewrote."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slopgate.installer.native.settings_guard import (
    NativeSettingsFile,
    SettingsGuard,
    capture_guards,
    restore_guards,
)

REGISTRY = frozenset({"packages"})
INERT = frozenset({"version"})
ORIGINAL = '{"theme": "dark"}\n'
STILL_REGISTERED = '{"packages": ["../ours"]}\n'
FOREIGN_KEY = '{"theme": "light", "packages": []}\n'

_EMPTIED_DOCUMENTS = st.fixed_dictionaries(
    {},
    optional={
        "packages": st.sampled_from(([], {})),
        "version": st.integers(),
    },
)
_FOREIGN_KEYS = st.text(min_size=1, max_size=8).filter(
    lambda key: key not in REGISTRY | INERT
)
_PROPERTY_SETTINGS = settings(max_examples=40)


@dataclass(frozen=True, slots=True)
class _Case:
    seeded: str | None
    after_host: str
    expected: str | None


_RESTORED = (
    _Case(None, '{"packages": []}\n', None),
    _Case(None, '{"version": 2, "packages": []}\n', None),
    _Case(ORIGINAL, '{"theme": "dark", "packages": []}\n', ORIGINAL),
)
_RESTORED_IDS = ("created-and-emptied", "created-with-inert-key", "existing-rewritten")
_REFUSED = (STILL_REGISTERED, FOREIGN_KEY, "not json")
_REFUSED_IDS = ("still-registered", "foreign-key", "unparseable")


def _guarded_file(path: Path, seeded: str | None) -> tuple[SettingsGuard, ...]:
    if seeded is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(seeded, encoding="utf-8")
    return capture_guards((NativeSettingsFile(path, REGISTRY, INERT),))


def _host_writes(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("case", _RESTORED, ids=_RESTORED_IDS)
def test_restore_guards_returns_the_file_to_its_prior_state(
    case: _Case, tmp_path: Path
) -> None:
    path = tmp_path / "config" / "settings.json"
    guards = _guarded_file(path, case.seeded)
    _host_writes(path, case.after_host)

    restore_guards(guards)

    text = path.read_text(encoding="utf-8") if path.exists() else None
    assert text == case.expected, (
        "restore must rewrite original bytes and delete a created file that only "
        "holds emptied registry keys"
    )


@pytest.mark.parametrize("after_host", _REFUSED, ids=_REFUSED_IDS)
def test_restore_guards_never_deletes_content_it_does_not_own(
    after_host: str, tmp_path: Path
) -> None:
    path = tmp_path / "config" / "settings.json"
    guards = _guarded_file(path, None)
    _host_writes(path, after_host)

    with pytest.raises(OSError, match="left in place"):
        restore_guards(guards)

    assert path.read_text(encoding="utf-8") == after_host, (
        "a created file with live registrations or foreign settings must be kept"
    )


def test_restore_guards_removes_only_created_directories(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    path = existing / "nested" / "deeper" / "settings.json"
    guards = _guarded_file(path, None)
    _host_writes(path, '{"packages": []}\n')

    restore_guards(guards)

    assert (existing.exists(), (existing / "nested").exists()) == (True, False), (
        "directories created for the settings file must be removed, but never "
        "the directory that already existed"
    )


@_PROPERTY_SETTINGS
@given(document=_EMPTIED_DOCUMENTS, foreign=_FOREIGN_KEYS)
def test_restore_guards_deletes_exactly_the_emptied_registry_documents(
    document: dict[str, object], foreign: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    emptied, kept, guards = _document_pair(tmp_path_factory, document, foreign)

    with pytest.raises(OSError, match="left in place"):
        restore_guards(guards)

    assert (emptied.exists(), kept.exists()) == (False, True), (
        "only the file holding nothing but emptied registry keys may be deleted"
    )


def _document_pair(
    factory: pytest.TempPathFactory, document: dict[str, object], foreign: str
) -> tuple[Path, Path, tuple[SettingsGuard, ...]]:
    root = factory.mktemp("guard")
    emptied, kept = root / "emptied.json", root / "kept.json"
    guards = capture_guards(
        tuple(NativeSettingsFile(path, REGISTRY, INERT) for path in (emptied, kept))
    )
    emptied.write_text(json.dumps(document), encoding="utf-8")
    kept.write_text(json.dumps({**document, foreign: 1}), encoding="utf-8")
    return emptied, kept, guards
