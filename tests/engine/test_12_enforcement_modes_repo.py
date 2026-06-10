"""Repo enrollment tests split from test_12_enforcement_modes."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.support import pretool_delete_payload
from tests.test_engine import (
    Path,
    pretool_write_payload,
    assert_denied_by,
    evaluate_payload,
    finding_ids,
)


def repo_with_quality_gate(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    return repo


def _patch_allowlist_payload(repo: Path) -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Patch",
        "tool_input": {
            "patch": """
*** Begin Patch
*** Update File: slopgate.toml
@@
 allowed_strings = [
+    "field",
+    "company",
 ]
*** End Patch
""".lstrip()
        },
    }


def _patch_delete_payload(repo: Path) -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Patch",
        "tool_input": {
            "patch": "*** Begin Patch\n*** Delete File: slopgate.toml\n*** End Patch\n"
        },
    }


def _direct_policy_marker_payload(repo: Path) -> dict[str, object]:
    return pretool_write_payload(
        repo,
        "slopgate.toml",
        """
[slopgate]
enabled = true
[magic_values]
allowed_strings = ["type", "value", "text", "status", "field", "company"]
[wrappers]
allowed = []
""".lstrip(),
    )


_REPO_ENROLLMENT_CASES: list[tuple[str, Callable[[Path], dict[str, object]]]] = [
    (
        "repo_enrolled_sentinel",
        lambda repo: pretool_write_payload(repo, ".noslopgate", ""),
    ),
    (
        "repo_enrolled_delete",
        lambda repo: pretool_delete_payload(repo, "slopgate.toml"),
    ),
    (
        "repo_enrolled_disable_flag",
        lambda repo: pretool_write_payload(
            repo, "slopgate.toml", "[slopgate]\nenabled = false\n"
        ),
    ),
    ("repo_enrolled_policy_marker_edit", _direct_policy_marker_payload),
    ("repo_enrolled_policy_marker_patch", _patch_allowlist_payload),
    ("repo_enrolled_patch_delete", _patch_delete_payload),
]


@pytest.mark.parametrize(("repo_name", "payload_builder"), _REPO_ENROLLMENT_CASES)
def test_repo_enrollment_rule_blocks_mutations(
    tmp_path: Path,
    repo_name: str,
    payload_builder: Callable[[Path], dict[str, object]],
) -> None:
    repo = repo_with_quality_gate(tmp_path, repo_name)
    result = evaluate_payload(payload_builder(repo))
    assert_denied_by(result, "REPO-ENROLL-001")
    assert "REPO-ENROLL-001" in finding_ids(result)
