"""Behavior checks for the reproducible OpenCode latency benchmark."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies

from slopgate.adapters.opencode_projection import OPENCODE_TOOL_CONTRACT_VERSION
from slopgate.benchmarks.opencode_latency.models import (
    BenchmarkConfig,
    BenchmarkExecutionError,
    BenchmarkRun,
    LatencySummary,
)
from slopgate.benchmarks.opencode_latency import plugin_runner
from slopgate.benchmarks.opencode_latency.plugin_runner import run_plugin

_MAX_BENCHMARK_TOTAL_MS = 10_000.0
_TOTAL_LATENCY_STRATEGY = strategies.floats(
    min_value=0.0, max_value=_MAX_BENCHMARK_TOTAL_MS, allow_nan=False
)
_PLUGIN_OUTCOME_STRATEGY = strategies.sampled_from(("returned", "blocked:policy"))
_PROJECTION_CONTRACT = "slopgate-opencode-projection-v1"


@contextmanager
def _missing_trace_case(
    total: float, outcome: str
) -> Iterator[tuple[BenchmarkConfig, subprocess.CompletedProcess[str]]]:
    with TemporaryDirectory(prefix="slopgate-benchmark-test-") as directory:
        repo = Path(directory)
        target = repo / "target.py"
        target.write_text("value = 1\n", encoding="utf-8")
        config = BenchmarkConfig(repo, target, 1, 0, "slopgate")
        completed = subprocess.CompletedProcess(
            args=["bun"],
            returncode=0,
            stdout=f'{{"totals":[{total}],"outcomes":["{outcome}"]}}',
            stderr="",
        )
        yield config, completed


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    summary = LatencySummary.from_values([5.0, 1.0, 4.0, 2.0, 3.0])

    assert summary.to_dict() == {
        "minimum": 1.0,
        "p50": 3.0,
        "p95": 5.0,
        "maximum": 5.0,
    }, "summary should report sorted nearest-rank percentiles"


def test_benchmark_run_preserves_observed_samples() -> None:
    run = BenchmarkRun(
        totals=[15.0],
        outcomes=["returned"],
        rows=[{"timing": {"evaluation_ms": 10, "subprocess_startup_ms": 2}}],
    )

    assert run.totals == [15.0], "run should preserve measured total latency"
    assert run.outcomes == ["returned"], "run should preserve plugin outcomes"
    assert run.rows[0]["timing"] == {
        "evaluation_ms": 10,
        "subprocess_startup_ms": 2,
    }, "run should preserve phase trace rows"


def test_projection_contract_is_release_independent() -> None:
    assert OPENCODE_TOOL_CONTRACT_VERSION == _PROJECTION_CONTRACT, (
        "OpenCode release updates must not change Slopgate's projection protocol"
    )


@given(
    total=_TOTAL_LATENCY_STRATEGY,
    outcome=_PLUGIN_OUTCOME_STRATEGY,
)
@settings(max_examples=10, deadline=None)
def test_run_plugin_rejects_success_without_result_trace(
    total: float, outcome: str
) -> None:
    with _missing_trace_case(total, outcome) as (config, completed):
        with (
            patch.object(plugin_runner.subprocess, "run", return_value=completed),
            pytest.raises(BenchmarkExecutionError, match="no result trace"),
        ):
            run_plugin(config, {})
