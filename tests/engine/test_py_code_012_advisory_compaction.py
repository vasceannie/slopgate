from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings, strategies
from slopgate.context import build_context
from slopgate.constants import POST_TOOL_USE, TOOL_WRITE
from slopgate.engine import evaluate_payload
from slopgate.engine.advisories import compact_context_advisories
from slopgate.models import EngineResult, RuleFinding, Severity

SESSION_A = "feature-envy-session-a"
SESSION_B = "feature-envy-session-b"
PROPERTY_EXAMPLES = 25
MIN_ACCESS_COUNT = 1
MAX_ACCESS_COUNT = 20
PROPERTY_PATH_SEGMENTS = strategies.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)
PROPERTY_ACCESS_COUNTS = strategies.integers(
    min_value=MIN_ACCESS_COUNT, max_value=MAX_ACCESS_COUNT
)
ENVY_SOURCE = """
service = object()


def render():
    return (
        service.alpha
        + service.beta
        + service.gamma
        + service.delta
        + service.epsilon
        + service.zeta
    )
"""
MULTI_ENVY_SOURCE = """
service = object()
other = object()


def render():
    return (
        service.alpha
        + service.beta
        + service.gamma
        + service.delta
        + service.epsilon
        + service.zeta
        + service.eta
    )


def summarize():
    return (
        other.alpha
        + other.beta
        + other.gamma
        + other.delta
        + other.epsilon
        + other.zeta
    )
"""


def write_payload(
    root: Path, rel_path: str, content: str, session_id: str
) -> dict[str, object]:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "hook_event_name": POST_TOOL_USE,
        "session_id": session_id,
        "tool_name": TOOL_WRITE,
        "tool_input": {"file_path": rel_path, "content": content},
        "cwd": str(root),
    }


def feature_envy_findings(
    root: Path, rel_path: str, content: str, session_id: str
) -> tuple[EngineResult, list[RuleFinding]]:
    result = evaluate_payload(write_payload(root, rel_path, content, session_id))
    findings = [item for item in result.findings if item.rule_id == "PY-CODE-012"]
    assert findings, "expected PY-CODE-012 finding"
    return result, findings


def compact_generated_first_hit(
    segment: str, access_count: int
) -> tuple[RuleFinding, str]:
    with TemporaryDirectory() as root_text:
        root = Path(root_text)
        rel_path = f"src/{segment}.py"
        (root / "slopgate.toml").write_text("", encoding="utf-8")
        ctx = build_context(write_payload(root, rel_path, ENVY_SOURCE, SESSION_A))
        finding = RuleFinding(
            rule_id="PY-CODE-012",
            title="Feature envy advisory",
            severity=Severity.LOW,
            message="first advisory stays visible",
            metadata={
                "path": rel_path,
                "accesses": access_count,
                "total": access_count,
            },
        )

        compact_context_advisories(ctx, [finding])

        expected_path = str((root / rel_path).resolve(strict=False))
        return finding, expected_path


def test_feature_envy_repeat_suppresses_same_session_path(tmp_path: Path) -> None:
    (tmp_path / "slopgate.toml").write_text("", encoding="utf-8")

    first_result, first_findings = feature_envy_findings(
        tmp_path, "src/envy.py", ENVY_SOURCE, SESSION_A
    )
    first = first_findings[0]
    repeat_result, repeat_findings = feature_envy_findings(
        tmp_path, "src/envy.py", ENVY_SOURCE, SESSION_A
    )
    repeat = repeat_findings[0]

    assert first_result.output is None, "first PY-CODE-012 hit should not block"
    assert first.message is not None, "first same-session/path hit should keep text"
    assert first.message.startswith(
        "Feature envy: src/envy.py:render overuses service"
    ), "first hit should show stable terse advisory text"
    assert repeat_result.output is None, "repeat PY-CODE-012 hit should not block"
    assert repeat.message is None, "repeat same-session/path hit should hide text"
    assert repeat.metadata["context_suppressed"] is True, (
        "repeat hit should remain visible through metadata"
    )
    assert repeat.metadata["repeat_count"] == 2, "repeat count should increment"


def test_compact_context_advisories_records_public_seam_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "slopgate.toml").write_text("", encoding="utf-8")
    ctx = build_context(
        write_payload(tmp_path, "src/direct.py", ENVY_SOURCE, SESSION_A)
    )
    findings = [
        RuleFinding(
            rule_id="PY-CODE-012",
            title="Feature envy advisory",
            severity=Severity.LOW,
            message="Feature envy: src/direct.py:render overuses service",
            metadata={"path": "src/direct.py", "accesses": 6, "total": 6},
        )
    ]

    compact_context_advisories(ctx, findings)

    assert findings[0].message is not None, "first direct advisory should keep text"
    assert findings[0].metadata["repeat_count"] == 1, "first direct hit starts at one"
    assert "normalized_path" in findings[0].metadata, "normalized path should be stored"


@settings(max_examples=PROPERTY_EXAMPLES)
@given(segment=PROPERTY_PATH_SEGMENTS, access_count=PROPERTY_ACCESS_COUNTS)
def test_compact_context_advisories_normalizes_first_hit_for_relative_paths(
    segment: str, access_count: int
) -> None:
    finding, expected_path = compact_generated_first_hit(segment, access_count)

    assert finding.message == "first advisory stays visible", (
        "first generated PY-CODE-012 hit should keep advisory text"
    )
    assert finding.metadata["repeat_count"] == 1, (
        "first generated PY-CODE-012 hit should start repeat count at one"
    )
    assert finding.metadata["normalized_path"] == expected_path, (
        "generated relative paths should normalize against the hook cwd"
    )


def test_feature_envy_compaction_tracks_path_and_session_separately(
    tmp_path: Path,
) -> None:
    (tmp_path / "slopgate.toml").write_text("", encoding="utf-8")
    _, _ = feature_envy_findings(tmp_path, "src/envy.py", ENVY_SOURCE, SESSION_A)

    _, path_findings = feature_envy_findings(
        tmp_path, "src/other_envy.py", ENVY_SOURCE, SESSION_A
    )
    _, session_findings = feature_envy_findings(
        tmp_path, "src/envy.py", ENVY_SOURCE, SESSION_B
    )

    assert path_findings[0].message is not None, "new paths should keep first message"
    assert path_findings[0].metadata["repeat_count"] == 1, "new path should start fresh"
    assert session_findings[0].message is not None, (
        "new sessions should keep first message"
    )
    assert session_findings[0].metadata["repeat_count"] == 1, (
        "new session should start fresh"
    )


def test_feature_envy_same_file_suppresses_lower_ratio_and_traces_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "slopgate.toml").write_text("", encoding="utf-8")

    result, findings = feature_envy_findings(
        tmp_path, "src/multi_envy.py", MULTI_ENVY_SOURCE, SESSION_A
    )
    visible_messages = [item.message for item in findings if item.message]
    suppressed = [item for item in findings if item.metadata.get("context_suppressed")]
    trace_text = (tmp_path / "slopgate_root" / "logs" / "results.jsonl").read_text(
        encoding="utf-8"
    )

    assert result.output is None, "pure PY-CODE-012 should not add dynamic output"
    assert len(findings) == 2, "both same-file PY-CODE-012 findings should survive"
    assert len(visible_messages) == 1, "only one same-file advisory message should show"
    assert (
        suppressed[0].metadata["context_suppression_reason"] == "same_path_lower_ratio"
    ), "same-file suppression should explain why text was hidden"
    assert '"context_suppressed": true' in trace_text, (
        "results JSONL should keep suppressed finding metadata"
    )
    assert '"decision": "context"' in trace_text, "results JSONL should keep decisions"
