"""Hook-layer tests — pytest + conftest fixtures + parametrize.
All shared fixtures (evaluate, load_fixture, pretool_write, pretool_bash,
bundle_root, tmp_project) live in conftest.py. Shared non-fixture helpers
live in tests.support and tests.engine_support.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from slopgate._types import ObjectDict, object_dict
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from slopgate.util.payloads import shell_command_paths
from tests import engine_support
from tests.support import (
    BUNDLE_ROOT,
    BashBuilder,
    EvaluateFn,
    LoadFixture,
    WriteBuilder,
    assert_asked_by,
    assert_blocked,
    assert_denied_by,
    assert_not_denied,
    finding_ids,
    hook_output,
    nested_output,
    output_string,
    pretool_delete_payload,
    require_output,
    required_string,
)

FIXTURE_FILE_NAMES = tuple(
    sorted((path.name for path in (BUNDLE_ROOT / "fixtures").glob("*.json")))
)

VALID_TOP_LEVEL_KEYS = {
    "decision",
    "reason",
    "hookSpecificOutput",
    "continue",
    "stopReason",
    "suppressOutput",
    "systemMessage",
}
EVENTS_NO_HOOK_SPECIFIC = (
    "Stop",
    "SubagentStop",
    "ConfigChange",
    "PostToolUseFailure",
    "TaskCompleted",
    "TeammateIdle",
)

VIRTUALENV_PARSE_SKIP_PATHS = engine_support.VIRTUALENV_PARSE_SKIP_PATHS
disabled_rule_findings = engine_support.disabled_rule_findings
rule_build_context = engine_support.rule_build_context
write_slopgate = engine_support.write_slopgate
assert_worktree_marker_copied = engine_support.assert_worktree_marker_copied
write_config_from_defaults = engine_support.write_config_from_defaults
enable_failing_post_edit_quality_command = (
    engine_support.enable_failing_post_edit_quality_command
)
disable_default_post_edit_quality = engine_support.disable_default_post_edit_quality
keep_default_config = engine_support.keep_default_config
latest_trace_event = engine_support.latest_trace_event
_set_skip_paths = engine_support._set_skip_paths
write_skip_paths_config = engine_support.write_skip_paths_config
post_edit_bash_payload = engine_support.post_edit_bash_payload
evaluate_post_edit_bash = engine_support.evaluate_post_edit_bash
strict_rule_id_sets = engine_support.strict_rule_id_sets
repo_with_moved_parse_error = engine_support.repo_with_moved_parse_error
_is_not_denied = engine_support._is_not_denied
assert_write_negative_case = engine_support.assert_write_negative_case
assert_bash_negative_case = engine_support.assert_bash_negative_case
init_git_worktree = engine_support.init_git_worktree
_fake_non_default_slopgate_git_output = engine_support._fake_non_default_slopgate_git_output
fake_slopgate_worktree_git_output = engine_support.fake_slopgate_worktree_git_output
pretool_write_payload = engine_support.pretool_write_payload
pretool_bash_payload = engine_support.pretool_bash_payload
evaluate_pretool_write = engine_support.evaluate_pretool_write
evaluate_pretool_bash = engine_support.evaluate_pretool_bash


def fixture_output(
    load_fixture: LoadFixture, fixture_name: str
) -> tuple[str, ObjectDict | None]:
    fixture_path = BUNDLE_ROOT / "fixtures" / fixture_name
    data = object_dict(cast(object, json.loads(fixture_path.read_text())))
    event = output_string(data, "hook_event_name", "unknown")
    result = evaluate_payload(load_fixture(fixture_name))
    return (event, result.output)


__all__ = (
    "BUNDLE_ROOT",
    "BashBuilder",
    "Callable",
    "EVENTS_NO_HOOK_SPECIFIC",
    "EngineResult",
    "EvaluateFn",
    "FIXTURE_FILE_NAMES",
    "LoadFixture",
    "MonkeyPatch",
    "ObjectDict",
    "Path",
    "VALID_TOP_LEVEL_KEYS",
    "VIRTUALENV_PARSE_SKIP_PATHS",
    "WriteBuilder",
    "assert_bash_negative_case",
    "assert_worktree_marker_copied",
    "assert_write_negative_case",
    "disable_default_post_edit_quality",
    "disabled_rule_findings",
    "enable_failing_post_edit_quality_command",
    "evaluate_post_edit_bash",
    "evaluate_pretool_bash",
    "evaluate_pretool_write",
    "_fake_non_default_slopgate_git_output",
    "fake_slopgate_worktree_git_output",
    "fixture_output",
    "init_git_worktree",
    "_is_not_denied",
    "keep_default_config",
    "latest_trace_event",
    "post_edit_bash_payload",
    "pretool_bash_payload",
    "pretool_delete_payload",
    "pretool_write_payload",
    "repo_with_moved_parse_error",
    "rule_build_context",
    "_set_skip_paths",
    "strict_rule_id_sets",
    "write_config_from_defaults",
    "write_slopgate",
    "write_skip_paths_config",
    "assert_blocked",
    "assert_denied_by",
    "assert_not_denied",
    "assert_asked_by",
    "cast",
    "evaluate_payload",
    "finding_ids",
    "hook_output",
    "json",
    "nested_output",
    "object_dict",
    "output_string",
    "pytest",
    "re",
    "require_output",
    "required_string",
    "shell_command_paths",
    "subprocess",
)
