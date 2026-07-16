from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings, strategies

from slopgate.context import build_context
from slopgate.rules.projected_lint.collectors import collect_projected_lint_report
from slopgate.rules.projected_lint.overlay import projected_overlay
from slopgate.rules.projected_lint.parity import (
    ProjectionParitySnapshot,
    pop_parity_snapshot,
    record_parity_snapshot,
)
from slopgate.rules.projected_lint.projection import (
    ProjectedFile,
    ProjectedFiles,
    build_projection,
)


IDENTIFIER = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True)
CONTENT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-\n",
    min_size=1,
    max_size=100,
)
IGNORED_REAL_PATH = Path()
COLLECTOR_IDS = strategies.dictionaries(
    keys=IDENTIFIER,
    values=strategies.lists(IDENTIFIER, min_size=1, max_size=3),
    max_size=3,
)


@given(name=IDENTIFIER, content=CONTENT)
def test_build_projection_preserves_complete_write_content_property(
    name: str,
    content: str,
) -> None:
    target = f"src/{name}.py"
    with TemporaryDirectory() as raw_root:
        result = build_projection(
            build_context(
                {
                    "session_id": "projected-property",
                    "cwd": raw_root,
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": target, "content": content},
                }
            )
        )

    assert isinstance(result, ProjectedFiles), "complete Write payloads should project"
    assert result.files[0].relative_path == target, (
        "projection should preserve target path"
    )
    assert result.files[0].content == content, (
        "projection should preserve exact content"
    )


@given(name=IDENTIFIER, content=CONTENT)
def test_projected_overlay_round_trips_content_and_cleans_up_property(
    name: str,
    content: str,
) -> None:
    relative_path = f"src/{name}.py"
    projected = ProjectedFile(relative_path, IGNORED_REAL_PATH, content)
    with TemporaryDirectory() as raw_repo:
        with projected_overlay(Path(raw_repo), (projected,)) as overlay:
            overlay_root = overlay.root
            materialized = overlay.files[0]
            observed = materialized.read_text(encoding="utf-8")

        assert observed == content, (
            "overlay materialization should preserve exact content"
        )
        assert materialized == overlay_root / relative_path, (
            "overlay materialization should preserve repository-relative paths"
        )
        assert not overlay_root.exists(), "overlay should always clean up after exit"


@settings(max_examples=15)
@given(name=IDENTIFIER, content=CONTENT)
def test_collect_projected_lint_report_preserves_target_paths_property(
    name: str,
    content: str,
) -> None:
    relative_path = f"src/{name}.py"
    with TemporaryDirectory() as raw_repo:
        repo = Path(raw_repo)
        target = repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        report = collect_projected_lint_report(repo, (target,))

    assert report.targets == [relative_path] or report.targets == [], (
        "Projected collector reports should keep repo-relative target paths"
    )


@settings(max_examples=25)
@given(collector_ids=COLLECTOR_IDS)
def test_parity_snapshot_pop_reports_match_for_same_collector_ids_property(
    collector_ids: dict[str, list[str]],
) -> None:
    paths = ["src/app.py"]
    normalized_ids = {
        collector: sorted(stable_ids) for collector, stable_ids in collector_ids.items()
    }
    parity = _pop_matching_parity(paths, normalized_ids)

    assert parity is not None, "Stored parity snapshots should be consumable"
    assert parity["status"] == "match", (
        "Equal projected and authoritative collector ids should report a match"
    )


def _pop_matching_parity(
    paths: list[str], collector_ids: dict[str, list[str]]
) -> dict[str, object] | None:
    with TemporaryDirectory() as raw_trace:
        trace_dir = Path(raw_trace)
        record_parity_snapshot(
            trace_dir,
            ProjectionParitySnapshot(
                session_id="session-a",
                paths=paths,
                collector_ids=collector_ids,
                projection_digest="digest-a",
            ),
        )
        return pop_parity_snapshot(trace_dir, "session-a", paths, collector_ids)
