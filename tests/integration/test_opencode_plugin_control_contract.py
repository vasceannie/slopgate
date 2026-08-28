from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from slopgate._types import object_dict
from tests.integration.opencode_plugin_control_support import (
    assert_recovery_protocol,
    run_plugin_contract,
)


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")


def test_file_edited_block_is_logged_without_throwing(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "file.edited")

    assert result.returncode == 0, result.stderr
    assert "contract block" in result.stdout


def test_typed_before_hook_still_throws_for_block(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before")

    assert result.returncode != 0
    assert "contract block" in result.stderr


def test_typed_after_hook_logs_detection_without_claiming_prevention(
    tmp_path: Path,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.after")
    expected_fragments = (
        "post-tool detection only",
        "no prevention or rollback occurred",
        "Repair is required before the next mutation",
    )

    assert result.returncode == 0, f"post-tool hook should not throw: {result.stderr}"
    assert all(fragment in result.stdout for fragment in expected_fragments), (
        f"post-tool detection log missing expected fragments: {result.stdout}"
    )


def test_installed_plugin_forwards_tool_contract_version(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before")

    assert result.returncode != 0
    assert "version=slopgate-opencode-projection-v1" in result.stderr


def test_pending_repair_blocks_unknown_effect_tool(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", "repair-required")

    assert result.returncode != 0, result.stderr
    assert_recovery_protocol(result.stderr)


def test_pending_repair_without_generation_uses_registered_verifier(
    tmp_path: Path,
) -> None:
    result = run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-required-unknown-generation",
    )

    assert result.returncode != 0, result.stderr
    assert_recovery_protocol(result.stderr)
    assert "generation unknown" in result.stderr, result.stderr
    assert "--generation unknown" not in result.stderr, result.stderr


@pytest.mark.parametrize(
    "response_mode",
    [
        pytest.param("repair-required-read-gitnexus", id="gitnexus-context"),
        pytest.param("repair-required-read-skill", id="skill-loader"),
    ],
)
def test_pending_repair_allows_trusted_read_only_tool(
    tmp_path: Path,
    response_mode: str,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "response_mode",
    [
        pytest.param(
            "repair-required-wrapper-interactive",
            id="interactive-shell-wrapper",
        ),
        pytest.param("repair-required-wrapper-skill-mcp", id="mcp-dispatch-wrapper"),
        pytest.param("repair-required-wrapper-task", id="task-delegation-wrapper"),
    ],
)
def test_pending_repair_blocks_opaque_wrappers(
    tmp_path: Path,
    response_mode: str,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode != 0, "opaque wrappers must not bypass pending repair"
    assert_recovery_protocol(result.stderr)


def test_pending_repair_allows_exact_lint_check_command(tmp_path: Path) -> None:
    result = run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-required-command-safe",
    )

    assert result.returncode == 0, result.stderr


def test_pending_repair_rejects_compound_lint_check_command(tmp_path: Path) -> None:
    result = run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-required-command-compound",
    )

    assert result.returncode != 0, "compound verification commands must remain blocked"
    assert_recovery_protocol(result.stderr)


@pytest.mark.parametrize(
    ("response_mode", "expected_error"),
    [
        ("repair-unavailable", "repair gate state"),
        ("repair-unavailable-read-collision", "repair gate state"),
        ("repair-unavailable-read-block", "contract block"),
    ],
)
def test_managed_repo_enforces_when_repair_state_is_unavailable(
    tmp_path: Path,
    response_mode: str,
    expected_error: str,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode != 0, (
        "managed repositories must fail closed on unreadable state"
    )
    assert expected_error in result.stderr, (
        "the plugin should explain why execution was denied"
    )


@pytest.mark.parametrize(
    ("response_mode", "expected_returncode"),
    [
        ("repair-unavailable-read", 0),
        ("repair-unavailable-apply-patch", 0),
        ("clean-enforcer-unavailable-apply-patch", 1),
    ],
)
def test_managed_repo_scopes_enforcer_failure_recovery(
    tmp_path: Path,
    response_mode: str,
    expected_returncode: int,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode == expected_returncode, result.stderr


def test_typed_before_hook_mutates_output_args_in_place(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", "mutate")
    observation = object_dict(json.loads(result.stdout))
    args = object_dict(observation.get("args"))

    assert args.get("content") == "mutated", "updated args must reach the host object"


def test_typed_hook_return_value_is_ignored(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", "mutate")
    observation = object_dict(json.loads(result.stdout))

    assert "hookReturn" not in observation, "typed hook must resolve without a value"


def test_generated_plugin_allows_unknown_effect_tool_in_clean_state(
    tmp_path: Path,
) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", "unknown-effect")

    assert result.returncode == 0, result.stderr


def test_generated_plugin_allows_unknown_read_only_tool(tmp_path: Path) -> None:
    result = run_plugin_contract(tmp_path, "tool.execute.before", "unknown-readonly")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("repo_mode", "response_mode"),
    (
        pytest.param("outside", "outside-unknown", id="outside-repo"),
        pytest.param("relaxed", "relaxed-unknown", id="relaxed-repo"),
    ),
)
def test_unknown_tool_is_advisory_outside_strict_repo(
    tmp_path: Path,
    repo_mode: str,
    response_mode: str,
) -> None:
    result = run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        response_mode,
        repo_mode,
    )

    assert result.returncode == 0, result.stderr
    assert "unknown OpenCode tool allowed" in result.stdout
