from __future__ import annotations

import json as _json

from tests.test_engine import (
    BashBuilder,
    Path,
    evaluate_payload,
    finding_ids,
    pytest,
)

class TestFindMutationsNotSafeRead:
    """find is only read-only when invoked without mutating predicates/actions."""

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("find .claude/hooks -delete", id="delete_predicate"),
            pytest.param(
                "find .claude/hooks -exec rm {} +",
                id="exec_rm_action",
            ),
        ],
    )
    def test_find_mutation_on_hook_path_blocked(
        self, pretool_bash: BashBuilder, command: str
    ) -> None:
        result = evaluate_payload(pretool_bash(command))
        blocked_rules = {
            "BUILTIN-PROTECTED-PATHS",
            "GLOBAL-BUILTIN-HOOK-INFRA-EXEC",
        }
        ids = finding_ids(result)
        assert ids & blocked_rules, (
            f"Expected protected hook path denial for {command!r}, got {ids}"
        )

class TestStopTranscriptReading:
    """STOP-001 should handle large transcripts without reading
    the entire file into memory."""

    def test_stop_001_detects_preexisting_in_stop_response(
        self, bundle_root: Path
    ) -> None:
        """Basic STOP-001 functionality."""
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "Stop",
            "stop_response": "These issues were pre-existing and not introduced by my changes.",
        }
        result = evaluate_payload(payload)
        assert "STOP-001" in finding_ids(result)

    def test_stop_001_clean_stop_allowed(self, bundle_root: Path) -> None:
        """Clean stop without dismissive language should pass."""
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "Stop",
            "stop_response": "All tasks complete. Tests pass. Quality gate clean.",
        }
        result = evaluate_payload(payload)
        assert "STOP-001" not in finding_ids(result)

    @staticmethod
    def _write_stop_transcript(
        tmp_path: Path, padding_count: int, final_text: str
    ) -> Path:
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            _json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": f"Working on step {i}..."}
                        ]
                    },
                }
            )
            for i in range(padding_count)
        ]
        lines.append(
            _json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": final_text}]},
                }
            )
        )
        _ = transcript.write_text("\n".join(lines))
        return transcript

    def test_stop_001_reads_transcript_file(
        self, bundle_root: Path, tmp_path: Path
    ) -> None:
        """STOP-001 should read from transcript_path when provided."""
        transcript = tmp_path / "transcript.jsonl"
        lines = [
            _json.dumps({"type": "user", "message": {"content": "fix the bug"}}),
            _json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "This was already existed before my changes.",
                            }
                        ]
                    },
                }
            ),
        ]
        _ = transcript.write_text("\n".join(lines))
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "Stop",
            "transcript_path": str(transcript),
        }
        result = evaluate_payload(payload)
        assert "STOP-001" in finding_ids(result)

    def test_stop_001_large_transcript_still_works(
        self, bundle_root: Path, tmp_path: Path
    ) -> None:
        """STOP-001 should handle large transcripts efficiently."""
        transcript = self._write_stop_transcript(
            tmp_path,
            padding_count=1000,
            final_text="These were pre-existing issues, not introduced by me.",
        )
        payload = {
            "session_id": "t",
            "cwd": str(bundle_root),
            "hook_event_name": "Stop",
            "transcript_path": str(transcript),
        }
        result = evaluate_payload(payload)
        assert "STOP-001" in finding_ids(result)

class TestTraceWriterInit:
    """TraceWriter should not duplicate mkdir calls that config already did."""

    def test_trace_writer_works_with_existing_dir(self, tmp_path: Path) -> None:
        from slopgate.trace import TraceWriter

        trace_dir = tmp_path / "logs"
        trace_dir.mkdir()
        (trace_dir / "async").mkdir()
        tw = TraceWriter(trace_dir)
        tw.event({"test": True})
        assert (trace_dir / "events.jsonl").exists()

    def test_trace_writer_works_with_missing_dir(self, tmp_path: Path) -> None:
        from slopgate.trace import TraceWriter

        trace_dir = tmp_path / "new_logs"
        tw = TraceWriter(trace_dir)
        tw.event({"test": True})
        assert (trace_dir / "events.jsonl").exists()

class TestRemindPytestMultiprocessing:
    """Advisory hook: when Claude runs pytest without -n flag,
    inject context reminding it to use pytest-xdist parallelism."""

    def test_plain_pytest_gets_reminder(self, pretool_bash: BashBuilder) -> None:
        """pytest tests/ without -n should trigger the reminder."""
        result = evaluate_payload(pretool_bash("pytest tests/ -v --tb=short"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" in ids

    def test_python_m_pytest_gets_reminder(self, pretool_bash: BashBuilder) -> None:
        """python -m pytest without -n should trigger the reminder."""
        result = evaluate_payload(pretool_bash("python -m pytest tests/"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" in ids

    def test_python3_m_pytest_gets_reminder(self, pretool_bash: BashBuilder) -> None:
        """python3 -m pytest without -n should trigger the reminder."""
        result = evaluate_payload(pretool_bash("python3 -m pytest tests/ -v"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" in ids

    def test_pytest_with_n_auto_no_reminder(self, pretool_bash: BashBuilder) -> None:
        """pytest -n auto should NOT trigger the reminder."""
        result = evaluate_payload(pretool_bash("pytest tests/ -n auto -v"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" not in ids

    def test_pytest_with_n_number_no_reminder(self, pretool_bash: BashBuilder) -> None:
        """pytest -n 4 should NOT trigger the reminder."""
        result = evaluate_payload(pretool_bash("pytest tests/ -n 4 --tb=short"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" not in ids

    def test_pytest_with_n_equals_no_reminder(self, pretool_bash: BashBuilder) -> None:
        """pytest -n=auto should NOT trigger the reminder."""
        result = evaluate_payload(pretool_bash("pytest -n=auto tests/"))
        ids = finding_ids(result)
        assert "REMIND-PYTEST-MP" not in ids

    def test_reminder_is_context_not_deny(self, pretool_bash: BashBuilder) -> None:
        """The rule should inject context, not block the command."""
        result = evaluate_payload(pretool_bash("pytest tests/"))
        reminder = next(
            (f for f in result.findings if f.rule_id == "REMIND-PYTEST-MP"), None
        )
        assert reminder is not None, "REMIND-PYTEST-MP not found in findings"
        assert reminder.decision is None, (
            "Should be advisory (context), not a deny/block"
        )
        assert reminder.additional_context, "Should have additional_context"
