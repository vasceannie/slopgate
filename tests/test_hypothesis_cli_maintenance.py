"""Property tests for the eval, stats, and path-command CLI surfaces."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies

from slopgate.cli.commands import cmd_eval, cmd_stats
from slopgate.cli.parsers.config import add_path_command_parser

ENGINE_MAX_EXAMPLES = 15
MAX_ROWS = 5

_PLATFORM_LISTS = strategies.lists(
    strategies.sampled_from(("claude", "nonsense")), max_size=MAX_ROWS
)
_PATH_ARGS = strategies.text(min_size=1).filter(lambda value: not value.startswith("-"))
_SESSION_IDS = strategies.lists(
    strategies.sampled_from(("session-a", "fixture-a", "test-a")), max_size=MAX_ROWS
)


def _eval_report(platforms: list[str]) -> tuple[int, dict[str, object]]:
    """Run ``cmd_eval`` on one Bash case per platform; return exit code and report."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "pack.jsonl"
        pack.write_text(
            "".join(
                json.dumps({"tier": "replayable", "platform": name, "replay_payload": payload})
                + "\n"
                for name in platforms
            ),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cmd_eval(argparse.Namespace(pack=str(pack)))
    return exit_code, json.loads(stdout.getvalue())


def _stats_report(session_ids: list[str]) -> dict[str, object]:
    """Run ``cmd_stats --json`` over one result row per session id."""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "results.jsonl"
        log.write_text(
            "".join(
                json.dumps(
                    {
                        "session_id": session_id,
                        "event_name": "Stop",
                        "tool_name": "Bash",
                        "timestamp": "2026-11-01T00:00:00+00:00",
                        "findings": [],
                    }
                )
                + "\n"
                for session_id in session_ids
            ),
            encoding="utf-8",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cmd_stats(argparse.Namespace(log=str(log), days=None, json=True))
    assert exit_code == 0, "stats over a readable log should exit cleanly"
    return json.loads(stdout.getvalue())


@settings(max_examples=ENGINE_MAX_EXAMPLES, deadline=None)
@given(platforms=_PLATFORM_LISTS)
def test_cmd_eval_exits_nonzero_exactly_when_a_case_fails(platforms: list[str]) -> None:
    failures = platforms.count("nonsense")

    exit_code, report = _eval_report(platforms)

    assert report["errors"] == failures, "only unknown platforms should fail replay"
    assert exit_code == (1 if failures else 0), "the exit code should reflect failures"


@settings(max_examples=ENGINE_MAX_EXAMPLES, deadline=None)
@given(session_ids=_SESSION_IDS)
def test_cmd_stats_accounts_for_every_row(session_ids: list[str]) -> None:
    fixtures = sum(session_id != "session-a" for session_id in session_ids)

    report = _stats_report(session_ids)

    assert report["fixture_filtered"] == fixtures, "fixture sessions should be set aside"
    assert report["analyzed_events"] == len(session_ids) - fixtures, (
        "every other row should be analyzed"
    )


@given(path=_PATH_ARGS)
def test_add_path_command_parser_round_trips_the_path_argument(path: str) -> None:
    parser = argparse.ArgumentParser()
    add_path_command_parser(
        parser.add_subparsers(dest="command"), "sample", help_text="Sample", func=str
    )

    assert parser.parse_args(["sample", path]).path == path, (
        "the positional path should reach the handler unchanged"
    )
