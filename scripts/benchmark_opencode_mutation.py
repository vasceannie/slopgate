#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6.0.3", "tomli>=2.4.1", "typing-extensions>=4.15.0"]
# ///
# How to run: uv run scripts/benchmark_opencode_mutation.py --iterations 10
"""Run the packaged OpenCode mutation-hook latency benchmark."""

from __future__ import annotations

from pathlib import Path
from runpy import run_module
import sys


_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))


if __name__ == "__main__":
    run_module("slopgate.benchmarks.opencode_latency.cli", run_name="__main__")
