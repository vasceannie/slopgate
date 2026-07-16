"""Activity statistics and feedback-evidence CLI surface."""

from __future__ import annotations

import argparse
from pathlib import Path

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.io import (
    CliInputError,
    int_arg,
    report_cli_input_error,
    string_arg,
)
from slopgate.stats import (
    FeedbackEvidenceRequest,
    export_feedback_loop_evidence,
    run_stats,
)
from slopgate.stats.evidence import InvalidSampleSizeError, RuleAuditMismatchError


def _cmd_stats(args: argparse.Namespace) -> int:
    """Report activity statistics or export a redacted denial sample."""
    export_path = string_arg(args, "export_evidence")
    if not export_path:
        return run_stats(
            log_path=string_arg(args, "log") or None,
            days=int_arg(args, "days"),
            as_json=bool(getattr(args, "json", False)),
        )

    try:
        summary = export_feedback_loop_evidence(
            FeedbackEvidenceRequest(
                log_path=(
                    Path(log_path) if (log_path := string_arg(args, "log")) else None
                ),
                output_path=Path(export_path),
                days=int_arg(args, "days"),
                sample_size=int_arg(args, "sample_size") or 100,
            )
        )
    except (InvalidSampleSizeError, RuleAuditMismatchError, OSError) as exc:
        return report_cli_input_error(CliInputError(str(exc)))
    print(
        f"Exported {summary.sample_count} of {summary.available_denials} "
        f"PY-LOG-002 denials to {summary.output_path}"
    )
    return 0


def _add_stats_parser(sub: SubparserRegistry) -> None:
    """Register the activity statistics command."""
    stats = sub.add_parser("stats", help="Analyze hook activity logs")
    stats.set_defaults(func=_cmd_stats)
    _ = stats.add_argument("--log")
    _ = stats.add_argument("--days", type=int)
    _ = stats.add_argument("--json", action="store_true")
    _ = stats.add_argument(
        "--export-evidence",
        help="Write a privacy-safe PY-LOG-002 denial sample to JSON",
    )
    _ = stats.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of recent PY-LOG-002 denials to export (default: 100)",
    )


add_stats_parser = _add_stats_parser
cmd_stats = _cmd_stats

__all__ = ["add_stats_parser", "cmd_stats"]
