"""Repair-gate CLI command handlers: status, verify, and clear."""

from __future__ import annotations

import argparse
import json
from slopgate._types import object_dict_list

from slopgate.state import HookStateCorruptionError

from ._scoping import (
    _invalid_repair_state,
    _load_repair_scope,
    _release_repair_generation,
)
from ._verification import _recorded_strings, _run_recorded_scope, _run_scoped_lint


def cmd_repair_status(args: argparse.Namespace) -> int:
    try:
        scope = _load_repair_scope(args)
    except (HookStateCorruptionError, ValueError) as exc:
        return _invalid_repair_state(exc)
    print(json.dumps(scope.required or {"status": "clean"}, sort_keys=True))
    return 0


def cmd_repair_verify(args: argparse.Namespace) -> int:
    try:
        scope = _load_repair_scope(args)
    except (HookStateCorruptionError, ValueError) as exc:
        return _invalid_repair_state(exc)
    required = scope.required
    if required is None:
        print(json.dumps({"status": "clean"}, sort_keys=True))
        return 0
    if required.get("generation") != args.generation:
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    targets = object_dict_list(required.get("targets"))
    if targets:
        completed = _run_scoped_lint(scope.root, targets)
    else:
        completed = _run_recorded_scope(
            scope.root,
            _recorded_strings(required.get("paths")),
            _recorded_strings(required.get("rule_ids")),
            invalid=(),
        )
    if completed != 0:
        return completed
    return _release_repair_generation(scope.store, args.generation)


def cmd_repair_clear(args: argparse.Namespace) -> int:
    """Clear one pending generation without verification (operator escape hatch).

    Agents cannot reach this during `REPAIR_REQUIRED`: the plugin and Python
    allowlists admit only declared read-only tools, `write`/`edit`/`apply_patch`,
    the repair verifier, and the exact `slopgate lint check` command.
    """
    try:
        scope = _load_repair_scope(args)
    except (HookStateCorruptionError, ValueError) as exc:
        return _invalid_repair_state(exc)
    if scope.required is None:
        print(json.dumps({"status": "clean"}, sort_keys=True))
        return 0
    return _release_repair_generation(scope.store, args.generation)
