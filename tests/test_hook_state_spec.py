from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from time import time
from typing import TypedDict

import pytest
from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.adapters import get_adapter
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult, RuleFinding, Severity
from slopgate.state import HookStateStore
from tests import hook_state_support
from tests.support import assert_denied_by, assert_not_denied, finding_ids

BUNDLE_ROOT = hook_state_support.BUNDLE_ROOT
_RESOURCES = hook_state_support._RESOURCES
_SubprocessFinding = hook_state_support._SubprocessFinding
_SubprocessResult = hook_state_support._SubprocessResult
InspectableHookStateStore = hook_state_support.InspectableHookStateStore
_normalize_subprocess_result = hook_state_support._normalize_subprocess_result
config_with_enabled_rules = hook_state_support.config_with_enabled_rules
enable_thin_wrapper_rule = hook_state_support.enable_thin_wrapper_rule
enable_loop_rules = hook_state_support.enable_loop_rules
ensure_enrolled = hook_state_support.ensure_enrolled
read_payload = hook_state_support.read_payload
bash_payload = hook_state_support.bash_payload
grep_payload = hook_state_support.grep_payload
posttool_payload = hook_state_support.posttool_payload
_THIN_WRAPPER_CODE = hook_state_support._THIN_WRAPPER_CODE
_thin_wrapper_payload = hook_state_support._thin_wrapper_payload
_evaluate_thin_wrapper_hit = hook_state_support._evaluate_thin_wrapper_hit
evaluate_thin_wrapper_hits = hook_state_support.evaluate_thin_wrapper_hits
run_thin_wrapper_subprocess_hit = hook_state_support.run_thin_wrapper_subprocess_hit
require_subprocess_finding = hook_state_support.require_subprocess_finding
repeat_tracking_repair_sequence = hook_state_support.repeat_tracking_repair_sequence
_python_subprocess_env = hook_state_support._python_subprocess_env
run_payload_in_subprocess = hook_state_support.run_payload_in_subprocess
_start_full_read_record_subprocess = hook_state_support._start_full_read_record_subprocess
start_full_read_record_processes = hook_state_support.start_full_read_record_processes
collect_process_failures = hook_state_support.collect_process_failures
missing_full_read_records = hook_state_support.missing_full_read_records
finding = hook_state_support.finding
require_finding = hook_state_support.require_finding
assert_repeat_counts = hook_state_support.assert_repeat_counts
assert_loop_steering_metadata = hook_state_support.assert_loop_steering_metadata


# Exported test support used by split test modules.
__all__ = (
    "BUNDLE_ROOT",
    "EngineResult",
    "HookStateStore",
    "Mapping",
    "ObjectDict",
    "Path",
    "RuleFinding",
    "Severity",
    "TypedDict",
    "InspectableHookStateStore",
    "_RESOURCES",
    "_SubprocessFinding",
    "_SubprocessResult",
    "_THIN_WRAPPER_CODE",
    "assert_loop_steering_metadata",
    "assert_repeat_counts",
    "bash_payload",
    "collect_process_failures",
    "config_with_enabled_rules",
    "enable_loop_rules",
    "enable_thin_wrapper_rule",
    "ensure_enrolled",
    "_evaluate_thin_wrapper_hit",
    "evaluate_thin_wrapper_hits",
    "finding",
    "grep_payload",
    "missing_full_read_records",
    "_normalize_subprocess_result",
    "posttool_payload",
    "_python_subprocess_env",
    "read_payload",
    "repeat_tracking_repair_sequence",
    "require_finding",
    "require_subprocess_finding",
    "run_payload_in_subprocess",
    "run_thin_wrapper_subprocess_hit",
    "start_full_read_record_processes",
    "_start_full_read_record_subprocess",
    "_thin_wrapper_payload",
    "assert_denied_by",
    "assert_not_denied",
    "evaluate_payload",
    "finding_ids",
    "get_adapter",
    "json",
    "object_dict",
    "object_list",
    "os",
    "pytest",
    "string_value",
    "subprocess",
    "sys",
    "time",
)
