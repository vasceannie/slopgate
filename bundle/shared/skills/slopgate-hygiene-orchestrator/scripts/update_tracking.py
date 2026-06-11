#!/usr/bin/env python3
"""Update hygiene tracking file with current progress."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_tracking(path: Path) -> dict:
    """Load existing tracking or create new."""
    if path.exists():
        return json.loads(path.read_text())
    return {
        "session_id": datetime.now(timezone.utc).isoformat(),
        "iteration": 0,
        "initial_counts": {},
        "current_counts": {},
        "completed_files": [],
        "pending_files": [],
        "blocked_issues": [],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def count_issues_from_unified(unified_path: Path) -> dict[str, int]:
    """Count issues from unified_issues.json."""
    if not unified_path.exists():
        return {}

    data = json.loads(unified_path.read_text())
    issues = data.get("issues", [])

    counts: dict[str, int] = {
        "python_errors": 0,
        "python_warnings": 0,
        "typescript_errors": 0,
        "typescript_warnings": 0,
        "rust_errors": 0,
        "rust_warnings": 0,
    }

    for issue in issues:
        source = issue.get("source", "")
        severity = issue.get("severity", "warning")

        if source in ("pyrefly", "basedpyright"):
            key = f"python_{severity}s"
        elif source in ("biome", "tsc"):
            key = f"typescript_{severity}s"
        elif source == "clippy":
            key = f"rust_{severity}s"
        else:
            continue

        if key in counts:
            counts[key] += 1

    return counts


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Update hygiene tracking file")
    parser.add_argument("hygiene_dir", type=Path, help="Path to .hygeine/ directory")
    parser.add_argument("--increment", action="store_true", help="Increment iteration counter")
    parser.add_argument("--complete-file", type=str, action="append", help="Mark file as completed")
    parser.add_argument("--block-file", type=str, nargs=2, metavar=("FILE", "REASON"), action="append", help="Block a file with reason")
    parser.add_argument("--init", action="store_true", help="Initialize tracking with current counts as initial")

    args = parser.parse_args()

    tracking_path = args.hygiene_dir / "tracking.json"
    unified_path = args.hygiene_dir / "unified_issues.json"

    tracking = load_tracking(tracking_path)

    # Get current counts
    current_counts = count_issues_from_unified(unified_path)

    if args.init or not tracking.get("initial_counts"):
        tracking["initial_counts"] = current_counts.copy()

    tracking["current_counts"] = current_counts

    if args.increment:
        tracking["iteration"] = tracking.get("iteration", 0) + 1

    if args.complete_file:
        completed = set(tracking.get("completed_files", []))
        completed.update(args.complete_file)
        tracking["completed_files"] = sorted(completed)

    if args.block_file:
        blocked = tracking.get("blocked_issues", [])
        for file_path, reason in args.block_file:
            if not any(b["file"] == file_path for b in blocked):
                blocked.append({"file": file_path, "reason": reason})
        tracking["blocked_issues"] = blocked

    # Update pending files from unified issues
    if unified_path.exists():
        data = json.loads(unified_path.read_text())
        all_files = set(data.get("by_file", {}).keys())
        completed = set(tracking.get("completed_files", []))
        blocked = {b["file"] for b in tracking.get("blocked_issues", [])}
        tracking["pending_files"] = sorted(all_files - completed - blocked)

    tracking["last_updated"] = datetime.now(timezone.utc).isoformat()

    tracking_path.write_text(json.dumps(tracking, indent=2))
    print(f"Updated {tracking_path}")

    # Print summary
    print(f"\nIteration: {tracking['iteration']}")
    print(f"Current counts: {tracking['current_counts']}")
    print(f"Completed files: {len(tracking['completed_files'])}")
    print(f"Pending files: {len(tracking['pending_files'])}")
    print(f"Blocked files: {len(tracking['blocked_issues'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
