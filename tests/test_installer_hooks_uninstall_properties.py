"""Decision-table properties for removing Slopgate entries from hooks.json."""

from __future__ import annotations

import json
from typing import NamedTuple, cast

import pytest
from hypothesis import HealthCheck, given, settings, strategies

from slopgate.installer._shared import (
    HooksUninstall,
    remove_owned_hooks,
    uninstall_hooks_file,
)

_OWNED_ENTRY: dict[str, object] = {
    "hooks": [{"type": "command", "command": "slopgate handle --platform codex"}]
}
_THIRD_PARTY_ENTRY: dict[str, object] = {
    "hooks": [{"type": "command", "command": "./existing.sh"}]
}
_EXTRA_SETTING = {"keep": True}
_DECISION_TABLE_EXAMPLES = 32


class _HooksDocument(NamedTuple):
    owned: bool
    third_party: bool
    extra_setting: bool
    dry_run: bool


class _UninstallOutcome(NamedTuple):
    status: int
    document: dict[str, object] | None


def _hooks_document(case: _HooksDocument) -> dict[str, object]:
    entries = [
        entry
        for present, entry in (
            (case.owned, _OWNED_ENTRY),
            (case.third_party, _THIRD_PARTY_ENTRY),
        )
        if present
    ]
    document: dict[str, object] = {"hooks": {"PreToolUse": entries}}
    if case.extra_setting:
        document.update(_EXTRA_SETTING)
    return document


def _expected_outcome(case: _HooksDocument) -> _UninstallOutcome:
    if case.dry_run:
        return _UninstallOutcome(0, _hooks_document(case))
    expected: dict[str, object] = dict(_EXTRA_SETTING) if case.extra_setting else {}
    if case.third_party:
        expected["hooks"] = {"PreToolUse": [_THIRD_PARTY_ENTRY]}
    return _UninstallOutcome(0, expected or None)


def _uninstall(
    factory: pytest.TempPathFactory, case: _HooksDocument
) -> _UninstallOutcome:
    root = factory.mktemp("hooks-root")
    hooks_path = root / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    _ = hooks_path.write_text(json.dumps(_hooks_document(case)), encoding="utf-8")
    status = uninstall_hooks_file(
        hooks_path,
        HooksUninstall(
            label="Codex",
            remove_owned=remove_owned_hooks,
            dry_run=case.dry_run,
            root=root,
        ),
    )
    document = (
        cast(dict[str, object], json.loads(hooks_path.read_text(encoding="utf-8")))
        if hooks_path.exists()
        else None
    )
    return _UninstallOutcome(status, document)


_HOOKS_DOCUMENTS = strategies.builds(_HooksDocument, *([strategies.booleans()] * 4))
_DECISION_TABLE = settings(
    deadline=None,
    max_examples=_DECISION_TABLE_EXAMPLES,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@_DECISION_TABLE
@given(case=_HOOKS_DOCUMENTS)
def test_uninstall_hooks_file_keeps_only_foreign_state_property(
    tmp_path_factory: pytest.TempPathFactory, case: _HooksDocument
) -> None:
    outcome = _uninstall(tmp_path_factory, case)

    assert outcome == _expected_outcome(case), (
        "uninstall removes only Slopgate hooks, keeps foreign hooks and settings, "
        "deletes the file once nothing foreign remains, and never writes on dry-run"
    )
