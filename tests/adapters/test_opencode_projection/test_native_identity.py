from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from .support import enroll_repo, projection_for, raw_payload, write_source


_NATIVE_MUTATION_ID_COLLISIONS = [
    pytest.param(
        "w_r_i_t_e",
        {"filePath": "src/app.py", "content": "VALUE = 2\n"},
        id="write-separator-collision",
    ),
    pytest.param(
        "apply__patch",
        {
            "patchText": (
                "*** Begin Patch\n*** Update File: src/app.py\n@@\n"
                "-VALUE = 1\n+VALUE = 2\n*** End Patch"
            )
        },
        id="apply-patch-separator-collision",
    ),
]


@pytest.mark.parametrize(("tool_name", "tool_input"), _NATIVE_MUTATION_ID_COLLISIONS)
def test_protocol_skew_blocks_native_mutation_id_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "VALUE = 1\n")
    payload = raw_payload(repo, tool_name, tool_input)
    payload["opencode_tool_contract_version"] = "wrong-contract"

    result = evaluate_payload(payload, platform="opencode")

    assert result.output is not None and result.output.get("action") == "block"
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "separator-collision tools must not inherit native mutation protocol deferral"


@pytest.mark.parametrize(("tool_name", "tool_input"), _NATIVE_MUTATION_ID_COLLISIONS)
def test_native_mutation_id_collision_is_not_projected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "VALUE = 1\n")

    projection = projection_for(repo, tool_name, tool_input)

    assert projection.get("status") == "unsupported"
