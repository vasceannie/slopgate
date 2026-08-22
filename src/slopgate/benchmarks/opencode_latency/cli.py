"""Benchmark the awaited OpenCode post-mutation hook through the real plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import sys

from .models import (
    BenchmarkConfig,
    BenchmarkExecutionError,
    BenchmarkRun,
    LatencySummary,
)
from .plugin_runner import run_plugin
from slopgate import __version__
from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.adapters.opencode_projection import OPENCODE_TOOL_CONTRACT_VERSION
from slopgate.config import GIT_BIN
from slopgate.constants import DECISION_KEY, METADATA_SLOPGATE, RULE_ID_KEY
from slopgate.installer._opencode import collect_opencode_install_identity


def _arguments() -> BenchmarkConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("src/slopgate/lint/_helpers/parsing.py"),
    )
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--binary", default="")
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    target = args.target if args.target.is_absolute() else repo / args.target
    if args.iterations < 2 or args.warmup < 0:
        parser.error("--iterations must be at least 2 and --warmup cannot be negative")
    if not target.is_file():
        parser.error(f"target does not exist: {target}")
    if not (repo / "slopgate.toml").is_file():
        parser.error(f"repository is not enrolled: {repo}")
    if shutil.which("bun") is None:
        parser.error("bun is required to drive the generated OpenCode plugin")
    local_binary = repo / ".venv" / "bin" / METADATA_SLOPGATE
    binary = args.binary or (
        str(local_binary)
        if local_binary.is_file()
        else shutil.which(METADATA_SLOPGATE)
    )
    if not binary:
        parser.error("slopgate binary not found; pass --binary explicitly")
    return BenchmarkConfig(repo, target.resolve(), args.iterations, args.warmup, binary)


def _repo_metadata(repo: Path, target: Path) -> ObjectDict:
    tracked = subprocess.run(
        [GIT_BIN, "ls-files", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    paths = [repo / item.decode() for item in tracked if item]
    existing = [path for path in paths if path.is_file()]
    content = target.read_bytes()
    return {
        "repo": str(repo),
        "tracked_files": len(existing),
        "tracked_bytes": sum(path.stat().st_size for path in existing),
        "target": str(target.relative_to(repo)),
        "touched_bytes": len(content),
        "content_fingerprint": hashlib.sha256(content).hexdigest(),
        "repo_fingerprint": hashlib.sha256(str(repo).encode()).hexdigest(),
        "tool_contract_fingerprint": OPENCODE_TOOL_CONTRACT_VERSION,
    }


def _phase_values(rows: list[ObjectDict], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = object_dict(row.get("timing")).get(key)
        if isinstance(value, int | float):
            values.append(float(value))
    return values


def _phase_report(run: BenchmarkRun) -> tuple[ObjectDict, str]:
    phases: ObjectDict = {}
    medians: dict[str, float] = {}
    phase_names = (
        "collector_ms",
        "evaluation_ms",
        "normalization_context_ms",
        "rule_engine_ms",
        "render_ms",
        "subprocess_startup_ms",
        "trace_event_ms",
    )
    for key in phase_names:
        values = _phase_values(run.rows, key)
        if values:
            summary = LatencySummary.from_values(values)
            phases[key] = summary.to_dict()
            medians[key] = summary.p50
    evaluation = _phase_values(run.rows, "evaluation_ms")
    subprocess_startup = _phase_values(run.rows, "subprocess_startup_ms")
    dispatch = [
        max(0.0, total - engine - startup)
        for total, engine, startup in zip(
            run.totals, evaluation, subprocess_startup, strict=True
        )
    ]
    dispatch_summary = LatencySummary.from_values(dispatch)
    phases["dispatch_ms"] = dispatch_summary.to_dict()
    medians["dispatch_ms"] = dispatch_summary.p50
    return phases, max(medians, key=medians.__getitem__)


def _finding_signature(row: ObjectDict) -> str:
    normalized: list[ObjectDict] = []
    for item in object_list(row.get("findings")):
        finding = object_dict(item)
        normalized.append(
            {
                key: finding.get(key)
                for key in (
                    "additional_context",
                    DECISION_KEY,
                    "message",
                    RULE_ID_KEY,
                    "severity",
                    "updated_input",
                )
            }
        )
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def _report(config: BenchmarkConfig, identity: ObjectDict, run: BenchmarkRun) -> ObjectDict:
    phases, dominant = _phase_report(run)
    finding_signatures = sorted({_finding_signature(row) for row in run.rows})
    decision_signatures = sorted({str(value) for value in run.outcomes})
    policies = {
        value
        for row in run.rows
        if isinstance((value := row.get("effective_policy_fingerprint")), str)
    }
    return {
        "benchmark": "opencode-awaited-post-mutation",
        "iterations": config.iterations,
        "warmup": config.warmup,
        "versions": identity,
        "sample": _repo_metadata(config.repo, config.target),
        "total_ms": LatencySummary.from_values(run.totals).to_dict(),
        "phases": phases,
        "dominant_phase": dominant,
        "decision_outcomes": run.outcomes,
        "decision_parity": len(decision_signatures) == 1,
        "finding_parity": len(finding_signatures) == 1,
        "finding_signatures": finding_signatures,
        "policy_fingerprints": sorted(policies),
    }


def main() -> int:
    config = _arguments()
    identity = collect_opencode_install_identity(config.binary)
    identity["slopgate_version"] = __version__
    try:
        run = run_plugin(config, identity)
    except BenchmarkExecutionError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(_report(config, identity, run), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
