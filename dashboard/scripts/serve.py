#!/usr/bin/env python3
"""Compatibility entry point for the ForceDash canvas server."""

import importlib
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

main = importlib.import_module("forcedash_server").main


if __name__ == "__main__":
    main()
